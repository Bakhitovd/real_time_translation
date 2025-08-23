"""
Module 6: System Audio Capture Handler
Backend handler for browser-based system audio capture and processing.
Integrates with existing translation pipeline for Zoom meeting translation.
"""

import io
import logging
import numpy as np
from typing import Dict, Tuple, Optional, Union
import wave
from pydub import AudioSegment
from pydub.utils import which

# Configure logging
logger = logging.getLogger(__name__)

class SystemAudioCaptureHandler:
    """Handles system audio capture from browser and prepares for translation pipeline."""
    
    def __init__(self, target_sample_rate: int = 16000, chunk_duration_ms: int = 3000):
        """
        Initialize system audio capture handler.
        
        Args:
            target_sample_rate: Target sample rate for processing (16kHz default)
            chunk_duration_ms: Duration of audio chunks in milliseconds
        """
        self.target_sample_rate = target_sample_rate
        self.chunk_duration_ms = chunk_duration_ms
        self.supported_formats = ['audio/webm', 'audio/wav', 'audio/mp3', 'audio/ogg']
        
        # Verify ffmpeg availability for pydub
        if not which("ffmpeg"):
            logger.warning("FFmpeg not found. Some audio formats may not be supported.")
    
    def validate_audio_data(self, audio_data: bytes) -> bool:
        """
        Validate incoming audio data.
        
        Args:
            audio_data: Raw audio bytes
            
        Returns:
            bool: True if valid audio data
        """
        if not audio_data:
            return False
        
        if len(audio_data) < 44:  # Minimum for WAV header
            return False
            
        # Check for common audio format headers
        headers = [
            b'RIFF',  # WAV
            b'OggS',  # OGG
            b'ID3',   # MP3
            b'\x1a\x45\xdf\xa3',  # WebM
            b'ftyp',  # MP4/M4A (may be at offset 4)
        ]
        
        # Check standard headers
        if any(audio_data.startswith(header) for header in headers):
            return True
            
        # Check M4A/MP4 format (ftyp box may be at offset 4)
        if len(audio_data) >= 8 and audio_data[4:8] == b'ftyp':
            return True
            
        return False
    
    def convert_to_wav(self, audio_data: bytes, source_format: str = 'webm') -> bytes:
        """
        Convert audio data to WAV format.

        Tries a sequence of strategies to maximize the chance of successful decoding:
         1. Use provided source_format hint (common for live capture flows).
         2. Detect likely container from header heuristics (ftyp/mp4, WebM, Ogg, MP3, WAV) and try that.
         3. Fall back to letting ffmpeg autodetect format by calling from_file without a format.

        Args:
            audio_data: Input audio bytes
            source_format: Source format hint ('webm', 'mp3', 'ogg', etc.)

        Returns:
            bytes: WAV format audio data

        Raises:
            ValueError: If conversion fails
        """
        def _export_to_wav(segment: AudioSegment) -> bytes:
            segment = segment.set_frame_rate(self.target_sample_rate)
            segment = segment.set_channels(1)
            segment = segment.set_sample_width(2)
            buf = io.BytesIO()
            segment.export(buf, format="wav")
            return buf.getvalue()

        # Strategy 1: try the provided hint first
        tried_formats = []
        try_variants = []

        if source_format:
            try_variants.append(source_format)

        # Strategy 2: header-based heuristics
        try:
            header = audio_data[:16] if len(audio_data) >= 16 else audio_data
            if audio_data.startswith(b'RIFF'):
                try_variants.append("wav")
            if audio_data.startswith(b'OggS'):
                try_variants.append("ogg")
            if audio_data.startswith(b'ID3'):
                try_variants.append("mp3")
            if audio_data.startswith(b'\x1a\x45\xdf\xa3'):
                try_variants.append("webm")
            if len(audio_data) >= 8 and audio_data[4:8] == b'ftyp':
                # MP4 / M4A container
                try_variants.append("mp4")
                try_variants.append("m4a")
        except Exception:
            # Ignore header parsing errors; we'll fall back to autodetect
            pass

        # Remove duplicates but preserve order
        seen = set()
        try_variants = [f for f in try_variants if not (f in seen or seen.add(f))]

        # Try each candidate format
        for fmt in try_variants:
            tried_formats.append(fmt)
            try:
                seg = AudioSegment.from_file(io.BytesIO(audio_data), format=fmt)
                return _export_to_wav(seg)
            except Exception:
                continue

        # Final strategy: attempt file-backed autodetection (more robust on Windows/ffmpeg builds)
        import tempfile
        tried_paths = []
        fallback_extensions = ["m4a", "mp4", "webm", "ogg", "mp3"]
        try:
            for ext in fallback_extensions:
                try:
                    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}")
                    tmp.write(audio_data)
                    tmp.flush()
                    tmp.close()
                    tried_paths.append(tmp.name)
                    seg = AudioSegment.from_file(tmp.name)
                    # Clean up temp files after successful read
                    for p in tried_paths:
                        try:
                            import os
                            os.remove(p)
                        except Exception:
                            pass
                    return _export_to_wav(seg)
                except Exception:
                    # try next extension
                    continue
        except Exception:
            pass

        # Last resort: in-memory autodetect (may fail on some ffmpeg builds)
        try:
            seg = AudioSegment.from_file(io.BytesIO(audio_data))
            return _export_to_wav(seg)
        except Exception as e_final:
            logger.error(f"Audio conversion failed for tried formats {tried_formats} and paths {tried_paths}: {e_final}")
            raise ValueError(f"Failed to convert audio: {e_final}")
    
    def extract_audio_info(self, wav_data: bytes) -> Dict[str, Union[int, float]]:
        """
        Extract audio metadata from WAV or other audio bytes.
        
        This function first tries to parse the input as a WAV stream (fast, no external
        dependencies). If that fails (e.g. for M4A/MP4, WebM, MP3), it uses pydub/ffmpeg
        to probe and extract metadata. Returns an empty dict on failure.
        """
        try:
            # Fast path for WAV data
            wav_buffer = io.BytesIO(wav_data)
            with wave.open(wav_buffer, 'rb') as wav_file:
                frames = wav_file.getnframes()
                sample_rate = wav_file.getframerate()
                channels = wav_file.getnchannels()
                sample_width = wav_file.getsampwidth()
                
                duration_seconds = frames / float(sample_rate) if sample_rate else 0.0
                
                return {
                    'format': 'wav',
                    'sample_rate': sample_rate,
                    'channels': channels,
                    'sample_width': sample_width,
                    'frames': frames,
                    'duration_seconds': duration_seconds,
                    'duration_ms': duration_seconds * 1000.0,
                    'size_bytes': len(wav_data)
                }
        except Exception as e_wav:
            # Fallback: try to use pydub/ffmpeg to read other formats (m4a/mp4, webm, mp3, ogg)
            try:
                audio_segment = AudioSegment.from_file(io.BytesIO(wav_data))
                # pydub uses milliseconds for length
                duration_ms = len(audio_segment)
                sample_rate = getattr(audio_segment, "frame_rate", None)
                channels = getattr(audio_segment, "channels", None)
                sample_width = getattr(audio_segment, "sample_width", None)
                
                # Try to detect format via header heuristics
                header = wav_data[:12] if len(wav_data) >= 12 else wav_data
                detected_format = None
                if wav_data.startswith(b'RIFF'):
                    detected_format = 'wav'
                elif wav_data.startswith(b'OggS'):
                    detected_format = 'ogg'
                elif wav_data.startswith(b'ID3'):
                    detected_format = 'mp3'
                elif wav_data.startswith(b'\x1a\x45\xdf\xa3'):
                    detected_format = 'webm'
                elif len(wav_data) >= 8 and wav_data[4:8] == b'ftyp':
                    detected_format = 'mp4/m4a'
                else:
                    detected_format = 'unknown'
                
                return {
                    'format': detected_format,
                    'sample_rate': sample_rate,
                    'channels': channels,
                    'sample_width': sample_width,
                    'frames': int((duration_ms / 1000.0) * sample_rate) if sample_rate else None,
                    'duration_seconds': duration_ms / 1000.0,
                    'duration_ms': duration_ms,
                    'size_bytes': len(wav_data)
                }
            except Exception as e_pydub:
                logger.error(f"Failed to extract audio info: {e_wav} | {e_pydub}")
                return {}
    
    def detect_speech_activity(self, wav_data: bytes, sensitivity: float = 0.01) -> Tuple[bool, float]:
        """
        Detect speech activity in audio data using a sensitivity parameter where higher values
        increase sensitivity (i.e. lower the energy threshold).

        Args:
            wav_data: WAV format audio bytes
            sensitivity: Sensitivity in range [0.0, 1.0]. Higher -> more sensitive detection.

        Returns:
            tuple: (has_speech, energy_level)
        """
        try:
            # Convert WAV to numpy array
            wav_buffer = io.BytesIO(wav_data)
            with wave.open(wav_buffer, 'rb') as wav_file:
                frames = wav_file.readframes(-1)
                audio_array = np.frombuffer(frames, dtype=np.int16)

            # Calculate RMS energy
            if len(audio_array) > 0:
                rms_energy = np.sqrt(np.mean(audio_array.astype(np.float32) ** 2))
                normalized_energy = rms_energy / 32768.0  # Normalize for 16-bit

                # Map sensitivity -> threshold: higher sensitivity => lower threshold
                try:
                    s = float(sensitivity)
                except Exception:
                    s = 0.01
                # Clamp sensitivity to [0.0, 1.0]
                s = max(0.0, min(1.0, s))
                base_threshold = 0.01
                threshold = base_threshold * max(0.0, (1.0 - s))

                # Debug logging for thresholds and energy (helps diagnose failing integration)
                logger.debug(f"[VAD] sensitivity={s}, threshold={threshold:.6f}, energy={normalized_energy:.6f}")

                has_speech = normalized_energy > threshold
                return has_speech, float(normalized_energy)

            return False, 0.0

        except Exception as e:
            logger.error(f"Speech activity detection failed: {e}")
            return False, 0.0
    
    def process_system_audio(self, audio_data: bytes, source_format: str = 'webm') -> Dict:
        """
        Process system audio data for translation pipeline.
        
        Args:
            audio_data: Raw audio bytes from browser
            source_format: Source audio format
            
        Returns:
            dict: Processed audio info with WAV data and metadata
        """
        result = {
            'success': False,
            'wav_data': None,
            'audio_info': {},
            'has_speech': False,
            'energy_level': 0.0,
            'error': None
        }
        
        try:
            # Log: audio received
            logger.info(f"[SystemAudio] Received audio data: {len(audio_data)} bytes, source_format={source_format}")

            # Validate input
            if not self.validate_audio_data(audio_data):
                logger.warning("[SystemAudio] Invalid audio data received")
                result['error'] = 'Invalid audio data'
                return result

            # Convert to WAV
            wav_data = self.convert_to_wav(audio_data, source_format)
            logger.info(f"[SystemAudio] Audio conversion to WAV successful: {len(wav_data)} bytes")

            # Extract metadata
            audio_info = self.extract_audio_info(wav_data)
            logger.info(f"[SystemAudio] Extracted audio info: {audio_info}")

            # Detect speech activity
            has_speech, energy_level = self.detect_speech_activity(wav_data)
            logger.info(f"[SystemAudio] VAD result: has_speech={has_speech}, energy_level={energy_level:.5f}")

            result.update({
                'success': True,
                'wav_data': wav_data,
                'audio_info': audio_info,
                'has_speech': has_speech,
                'energy_level': energy_level
            })

            logger.info(f"[SystemAudio] Processing complete: success={result['success']}, error={result['error']}, info={audio_info}")

        except Exception as e:
            logger.error(f"System audio processing failed: {e}")
            result['error'] = str(e)

        return result


def create_system_audio_handler(sample_rate: int = 16000, chunk_duration: int = 3000) -> SystemAudioCaptureHandler:
    """
    Factory function to create SystemAudioCaptureHandler instance.
    
    Args:
        sample_rate: Target sample rate for audio processing
        chunk_duration: Duration of audio chunks in milliseconds
        
    Returns:
        SystemAudioCaptureHandler: Configured handler instance
    """
    return SystemAudioCaptureHandler(sample_rate, chunk_duration)


def process_system_audio(audio_data: bytes, source_format: str = 'webm', sensitivity: float = 0.01) -> Dict:
    """
    Standalone function to process system audio data.
    
    Args:
        audio_data: Raw audio bytes from browser
        source_format: Source audio format
        sensitivity: Speech detection sensitivity threshold
        
    Returns:
        dict: Processed audio info with WAV data and metadata
    """
    handler = create_system_audio_handler()
    result = handler.process_system_audio(audio_data, source_format)
    
    # Update speech detection with custom sensitivity
    if result['success'] and result['wav_data']:
        has_speech, energy_level = handler.detect_speech_activity(result['wav_data'], sensitivity)
        result.update({
            'has_speech': has_speech,
            'energy_level': energy_level
        })
        
        # Rename wav_data to wav_audio for compatibility with tests
        result['wav_audio'] = result['wav_data']
        result['metadata'] = result['audio_info']
    
    return result


def is_system_audio_supported() -> bool:
    """
    Check if system audio capture is supported in current environment.
    
    Returns:
        bool: True if system audio capture dependencies are available
    """
    try:
        # Check for required dependencies
        import pydub
        return True
    except ImportError:
        return False
