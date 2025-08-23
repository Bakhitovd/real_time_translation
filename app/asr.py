"""
ASR (Automatic Speech Recognition) module.
Wraps local Whisper model for streaming audio transcription.
"""

import io
import logging
import tempfile
import time
import numpy as np
from faster_whisper import WhisperModel
from typing import Optional
import soundfile as sf
import os
from .temp_file_manager import managed_temp_file, write_bytes_to_temp_file, safe_file_delete
from app.utils import validate_wav_format

class StreamingASR:
    """Streaming ASR using faster-whisper for real-time transcription."""
    
    def __init__(self, model_size: str = "small", device: str = "cpu"):
        """Initialize Whisper model.
        
        Args:
            model_size: Whisper model size (tiny, base, small, medium, large)
            device: Device to run on (cpu, cuda)
        """
        self.model = WhisperModel(model_size, device=device)
        self.model_size = model_size
        self.device = device
        logging.info(f"Initialized Whisper ASR with model '{model_size}' on {device}")
    
    def transcribe_chunk(self, audio_bytes: bytes, language: Optional[str] = None) -> str:
        """Transcribe an audio chunk and return transcript.

        Args:
            audio_bytes: Raw audio bytes (WAV format expected)
            language: Source language code (None for auto-detect)

        Returns:
            Transcribed text string
        """
        try:
            # Basic validation: ensure we have a plausible WAV
            if not audio_bytes or len(audio_bytes) < 100:
                logging.warning("[ASR] Audio chunk too small to transcribe")
                return ""

            # Validate WAV header where possible to avoid passing invalid data to Whisper
            try:
                is_wav = validate_wav_format(audio_bytes)
            except Exception:
                is_wav = False

            if not is_wav:
                logging.warning("[ASR] Input audio does not appear to be valid WAV; proceeding but result may be empty")

            max_attempts = 2
            for attempt in range(1, max_attempts + 1):
                try:
                    # Use managed temporary file with guaranteed cleanup
                    with managed_temp_file(suffix=".wav", prefix="asr_") as temp_path:
                        # Write audio bytes to temporary file
                        with open(temp_path, 'wb') as f:
                            f.write(audio_bytes)

                        # Transcribe using faster-whisper (may raise)
                        segments, info = self.model.transcribe(
                            temp_path,
                            language=language,
                            task="transcribe",
                            vad_filter=True,
                            vad_parameters=dict(min_silence_duration_ms=500)
                        )

                        # Combine all segments into transcript
                        transcript = " ".join([segment.text.strip() for segment in segments if getattr(segment, "text", None)])

                        # Log transcript and metadata at INFO level
                        lang = getattr(info, "language", None)
                        lang_prob = getattr(info, "language_probability", None)
                        duration = getattr(info, "duration", None)
                        logging.info(
                            f"[ASR] Transcribed chunk (attempt {attempt}): '{transcript[:100]}', "
                            f"lang={lang}, lang_prob={lang_prob}, duration={duration}s, audio_len={len(audio_bytes)} bytes"
                        )

                        return transcript.strip()

                except Exception as inner_e:
                    logging.warning(f"[ASR] Transcription attempt {attempt} failed: {inner_e}")
                    # small backoff before retrying
                    if attempt < max_attempts:
                        time.sleep(0.2 * attempt)
                        continue
                    else:
                        logging.error(f"[ASR] All {max_attempts} transcription attempts failed for this chunk")
                        return ""

        except Exception as e:
            logging.error(f"ASR transcription failed: {e}")
            return ""

# Global ASR instance for reuse (avoid reloading model)
_asr_instance = None

def get_asr_instance(model_size: str = "small", device: str = "cpu") -> StreamingASR:
    """Get global ASR instance, creating if needed."""
    global _asr_instance
    if _asr_instance is None:
        _asr_instance = StreamingASR(model_size, device)
    return _asr_instance

def preload_model(model_size: str = "small", device: str = "cpu") -> None:
    """Preload the Whisper model to eliminate first-request delay.
    
    Args:
        model_size: Whisper model size (tiny, base, small, medium, large)
        device: Device to run on (cpu, cuda)
    """
    global _asr_instance
    logging.info(f"Preloading Whisper model '{model_size}' on {device}...")
    
    import time
    start_time = time.time()
    
    # Initialize the model
    _asr_instance = StreamingASR(model_size, device)
    init_time = time.time() - start_time
    logging.info(f"Whisper model initialized in {init_time:.2f}s")
    
    # Warm up the model with a test transcription
    logging.info("Warming up Whisper model with test audio...")
    warmup_start = time.time()
    
    try:
        # Create a small test WAV file (1 second of silence)
        import wave
        import numpy as np
        test_audio = np.zeros(16000, dtype=np.int16)  # 1 second at 16kHz
        
        # Use managed temporary file for warmup
        with managed_temp_file(suffix=".wav", prefix="asr_warmup_") as temp_path:
            with wave.open(temp_path, 'wb') as wav_file:
                wav_file.setnchannels(1)  # mono
                wav_file.setsampwidth(2)  # 16-bit
                wav_file.setframerate(16000)  # 16kHz
                wav_file.writeframes(test_audio.tobytes())
            
            # Perform test transcription to warm up the model
            with open(temp_path, 'rb') as f:
                test_audio_bytes = f.read()
            test_result = _asr_instance.transcribe_chunk(test_audio_bytes)
            warmup_time = time.time() - warmup_start
            
            logging.info(f"Whisper model warmed up in {warmup_time:.2f}s (test result: '{test_result}')")
            
    except Exception as e:
        warmup_time = time.time() - warmup_start
        logging.warning(f"Whisper model warmup failed in {warmup_time:.2f}s: {e}")
    
    total_time = time.time() - start_time
    logging.info(f"Whisper model preloading completed in {total_time:.2f}s total")

def transcribe_chunk(audio_bytes: bytes, language: Optional[str] = None) -> str:
    """Convenience function to transcribe audio chunk using global ASR instance.
    
    Args:
        audio_bytes: Raw audio bytes (WAV format expected)
        language: Source language code (None for auto-detect)
        
    Returns:
        Transcribed text string
    """
    asr = get_asr_instance()
    return asr.transcribe_chunk(audio_bytes, language)
