"""
ASR (Automatic Speech Recognition) module.
Wraps local Whisper model for streaming audio transcription.
"""

import io
import logging
import tempfile
import numpy as np
from faster_whisper import WhisperModel
from typing import Optional
import soundfile as sf
import os

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
            # Create temporary file from audio bytes
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                temp_file.write(audio_bytes)
                temp_path = temp_file.name
            
            # Transcribe using faster-whisper
            segments, info = self.model.transcribe(
                temp_path, 
                language=language, 
                task="transcribe",
                vad_filter=True,  # Voice activity detection
                vad_parameters=dict(min_silence_duration_ms=500)
            )
            
            # Combine all segments into transcript
            transcript = " ".join([segment.text.strip() for segment in segments])
            
            # Clean up temp file
            os.unlink(temp_path)
            
            logging.debug(f"ASR transcribed: '{transcript[:50]}...' (duration: {info.duration:.1f}s)")
            return transcript.strip()
            
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
