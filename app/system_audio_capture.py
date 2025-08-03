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
        
        Args:
            audio_data: Input audio bytes
            source_format: Source format hint ('webm', 'mp3', 'ogg', etc.)
            
        Returns:
            bytes: WAV format audio data
            
        Raises:
            ValueError: If conversion fails
        """
        try:
            # Create audio segment from bytes
            audio_segment = AudioSegment.from_file(
                io.BytesIO(audio_data), 
                format=source_format
            )
            
            # Convert to target specifications
            audio_segment = audio_segment.set_frame_rate(self.target_sample_rate)
            audio_segment = audio_segment.set_channels(1)  # Mono
            audio_segment = audio_segment.set_sample_width(2)  # 16-bit
            
            # Export to WAV bytes
            wav_buffer = io.BytesIO()
            audio_segment.export(wav_buffer, format='wav')
            return wav_buffer.getvalue()
            
        except Exception as e:
            logger.error(f"Audio conversion failed: {e}")
            raise ValueError(f"Failed to convert audio: {e}")
    
    def extract_audio_info(self, wav_data: bytes) -> Dict[str, Union[int, float]]:
        """
        Extract audio metadata from WAV data.
        
        Args:
            wav_data: WAV format audio bytes
            
        Returns:
            dict: Audio metadata (sample_rate, channels, duration_ms, etc.)
        """
        try:
            wav_buffer = io.BytesIO(wav_data)
            with wave.open(wav_buffer, 'rb') as wav_file:
                frames = wav_file.getnframes()
                sample_rate = wav_file.getframerate()
                channels = wav_file.getnchannels()
                sample_width = wav_file.getsampwidth()
                
                duration_ms = (frames / sample_rate) * 1000
                
                return {
                    'sample_rate': sample_rate,
                    'channels': channels,
                    'sample_width': sample_width,
                    'frames': frames,
                    'duration_ms': duration_ms,
                    'size_bytes': len(wav_data)
                }
        except Exception as e:
            logger.error(f"Failed to extract audio info: {e}")
            return {}
    
    def detect_speech_activity(self, wav_data: bytes, threshold: float = 0.01) -> Tuple[bool, float]:
        """
        Detect speech activity in audio data.
        
        Args:
            wav_data: WAV format audio bytes
            threshold: Energy threshold for speech detection
            
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
