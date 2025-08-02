"""
Text-to-Speech (TTS) module.
Wraps local TTS engine (pyttsx3 or Coqui) for speech synthesis.
"""

import io
import logging
import tempfile
import wave
import pyttsx3
from typing import Optional
import os

class StreamingTTS:
    """Text-to-Speech using pyttsx3 for real-time synthesis."""
    
    def __init__(self, voice: Optional[str] = None, rate: int = 150, volume: float = 0.9):
        """Initialize TTS engine.
        
        Args:
            voice: Voice ID to use (None for default)
            rate: Speech rate (words per minute)
            volume: Volume level (0.0 to 1.0)
        """
        self.engine = pyttsx3.init()
        
        # Configure voice
        if voice:
            voices = self.engine.getProperty('voices')
            for v in voices:
                if voice in v.id or voice in v.name:
                    self.engine.setProperty('voice', v.id)
                    break
        
        # Configure speech parameters
        self.engine.setProperty('rate', rate)
        self.engine.setProperty('volume', volume)
        
        logging.info(f"Initialized TTS engine with rate={rate}, volume={volume}")
    
    def synthesize_text(self, text: str) -> bytes:
        """Generate speech audio bytes from text.
        
        Args:
            text: Text to synthesize
            
        Returns:
            WAV audio bytes
        """
        if not text.strip():
            return b""
        
        try:
            # Create temporary file for audio output
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                temp_path = temp_file.name
            
            # Save audio to temporary file
            self.engine.save_to_file(text, temp_path)
            self.engine.runAndWait()
            
            # Read audio bytes from file
            with open(temp_path, 'rb') as f:
                audio_bytes = f.read()
            
            # Clean up temporary file
            os.unlink(temp_path)
            
            logging.debug(f"TTS synthesized: '{text[:30]}...' ({len(audio_bytes)} bytes)")
            return audio_bytes
            
        except Exception as e:
            logging.error(f"TTS synthesis failed: {e}")
            return b""
    
    def get_available_voices(self) -> list:
        """Get list of available voices."""
        voices = self.engine.getProperty('voices')
        return [(v.id, v.name) for v in voices] if voices else []

# Global TTS instance for reuse
_tts_instance = None

def get_tts_instance(voice: Optional[str] = None, rate: int = 150, volume: float = 0.9) -> StreamingTTS:
    """Get global TTS instance, creating if needed."""
    global _tts_instance
    if _tts_instance is None:
        _tts_instance = StreamingTTS(voice, rate, volume)
    return _tts_instance

def synthesize_text(text: str, voice: Optional[str] = None) -> bytes:
    """Convenience function to synthesize text using global TTS instance.
    
    Args:
        text: Text to synthesize
        voice: Voice to use (None for default)
        
    Returns:
        WAV audio bytes
    """
    tts = get_tts_instance(voice)
    return tts.synthesize_text(text)

def list_voices() -> list:
    """List available TTS voices."""
    tts = get_tts_instance()
    return tts.get_available_voices()

def initialize_tts(voice: Optional[str] = None, rate: int = 150, volume: float = 0.9) -> None:
    """Initialize TTS engine at startup to eliminate first-request delay.
    
    Args:
        voice: Voice to use (None for default)
        rate: Speech rate (words per minute)
        volume: Volume level (0.0 to 1.0)
    """
    global _tts_instance
    logging.info("Initializing TTS engine...")
    _tts_instance = StreamingTTS(voice, rate, volume)
    
    # Test synthesis to ensure everything works
    try:
        test_audio = _tts_instance.synthesize_text("System initialized")
        if test_audio:
            logging.info("TTS engine test synthesis successful")
        else:
            logging.warning("TTS engine test synthesis failed")
    except Exception as e:
        logging.warning(f"TTS engine test failed: {e}")

def cleanup_tts() -> None:
    """Clean up TTS engine resources."""
    global _tts_instance
    if _tts_instance and _tts_instance.engine:
        try:
            _tts_instance.engine.stop()
            logging.info("TTS engine stopped")
        except:
            pass
    _tts_instance = None
