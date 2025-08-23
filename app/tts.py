"""
Text-to-Speech (TTS) module.
Improved robustness: thread-safety, controlled run timeout, safe temp-file handling and retries.
Wraps local TTS engine (pyttsx3 or Coqui) for speech synthesis.
"""

import io
import logging
import time
import threading
from typing import Optional
import os

import pyttsx3

from app.temp_file_manager import managed_temp_file, safe_file_delete

class StreamingTTS:
    """Text-to-Speech using pyttsx3 for real-time synthesis with robustness improvements."""
    
    def __init__(self, voice: Optional[str] = None, rate: int = 150, volume: float = 0.9):
        """Initialize TTS engine.
        
        Args:
            voice: Voice ID to use (None for default)
            rate: Speech rate (words per minute)
            volume: Volume level (0.0 to 1.0)
        """
        # Use a re-entrant lock to ensure thread-safe access to the engine
        self._lock = threading.RLock()
        try:
            self.engine = pyttsx3.init()
        except Exception as e:
            logging.error(f"[TTS] Failed to initialize pyttsx3 engine: {e}")
            # Keep engine attribute for callers; set to None on failure
            self.engine = None
        
        # Configure voice if engine available
        if self.engine:
            try:
                if voice:
                    voices = self.engine.getProperty('voices')
                    for v in voices:
                        if voice in v.id or voice in v.name:
                            self.engine.setProperty('voice', v.id)
                            break
                # Configure speech parameters
                self.engine.setProperty('rate', rate)
                self.engine.setProperty('volume', volume)
            except Exception as e:
                logging.warning(f"[TTS] Warning configuring engine properties: {e}")
        
        self._configured_voice = voice
        logging.info(f"Initialized TTS engine with rate={rate}, volume={volume}, voice={voice}")
    
    def synthesize_text(self, text: str, run_timeout: float = 15.0, max_attempts: int = 2) -> bytes:
        """Generate speech audio bytes from text.
        
        Args:
            text: Text to synthesize
            run_timeout: Max seconds to wait for runAndWait to finish per attempt
            max_attempts: Number of attempts for synthesis before failing
        
        Returns:
            WAV audio bytes (empty bytes on failure)
        """
        if not text or not text.strip():
            return b""
        
        if self.engine is None:
            logging.error("[TTS] No TTS engine available")
            return b""
        
        attempt = 0
        while attempt < max_attempts:
            attempt += 1
            try:
                # Use managed temporary file to ensure the file is created and cleaned up
                with managed_temp_file(suffix=".wav", prefix="tts_", delete_on_exit=False) as temp_path:
                    # Save to file under engine lock
                    with self._lock:
                        try:
                            self.engine.save_to_file(text, temp_path)
                        except Exception as e:
                            logging.error(f"[TTS] save_to_file failed on attempt {attempt}: {e}")
                            raise
                        
                        # Run the engine in a dedicated thread so we can enforce a timeout
                        runner = threading.Thread(target=self._run_engine, daemon=True)
                        runner.start()
                        runner.join(timeout=run_timeout)
                        
                        if runner.is_alive():
                            logging.warning(f"[TTS] runAndWait did not finish within {run_timeout}s, attempting to stop engine")
                            try:
                                # Attempt to stop the engine to interrupt runAndWait
                                self.engine.stop()
                            except Exception as e:
                                logging.warning(f"[TTS] engine.stop() failed: {e}")
                            # Allow a short grace period
                            runner.join(timeout=2.0)
                            if runner.is_alive():
                                logging.error("[TTS] runAndWait thread still alive after stop attempt")
                                # Continue to attempt reading file (may be incomplete) or retry below
                        
                    # Read generated WAV bytes
                    audio_bytes = b""
                    if os.path.exists(temp_path):
                        try:
                            with open(temp_path, "rb") as f:
                                audio_bytes = f.read()
                        except Exception as e:
                            logging.error(f"[TTS] Failed to read temp WAV file '{temp_path}': {e}")
                            audio_bytes = b""
                        finally:
                            # Attempt cleanup; log but do not raise on failure
                            try:
                                safe_file_delete(temp_path)
                            except Exception:
                                logging.warning(f"[TTS] Could not delete temp file {temp_path}")
                    else:
                        logging.error(f"[TTS] Expected temp WAV not found: {temp_path}")
                    
                    if audio_bytes:
                        logging.info(f"[TTS] Synthesized speech (attempt {attempt}), bytes={len(audio_bytes)}")
                        return audio_bytes
                    else:
                        logging.warning(f"[TTS] Synthesis produced no audio on attempt {attempt}")
                        # fallthrough to retry if attempts remain
            except Exception as e:
                logging.error(f"[TTS] Synthesis attempt {attempt} failed: {e}")
                # small backoff before retrying
                time.sleep(0.5 * attempt)
        
        logging.error("[TTS] All synthesis attempts failed")
        return b""
    
    def _run_engine(self):
        """Helper to run the pyttsx3 engine; kept small to allow timeout management."""
        try:
            # runAndWait will block until all queued commands are processed
            self.engine.runAndWait()
        except Exception as e:
            logging.debug(f"[TTS] runAndWait raised: {e}")
    
    def get_available_voices(self) -> list:
        """Get list of available voices in a safe manner."""
        if self.engine is None:
            return []
        try:
            voices = self.engine.getProperty('voices')
            return [(v.id, v.name) for v in voices] if voices else []
        except Exception as e:
            logging.warning(f"[TTS] get_available_voices failed: {e}")
            return []

# Global TTS instance for reuse
_tts_instance = None
_tts_lock = threading.RLock()

def get_tts_instance(voice: Optional[str] = None, rate: int = 150, volume: float = 0.9) -> StreamingTTS:
    """Get global TTS instance, creating if needed (thread-safe)."""
    global _tts_instance
    with _tts_lock:
        if _tts_instance is None:
            _tts_instance = StreamingTTS(voice, rate, volume)
        return _tts_instance

def synthesize_text(text: str, voice: Optional[str] = None, rate: int = 150, volume: float = 0.9) -> bytes:
    """Convenience function to synthesize text using global TTS instance.
    
    Args:
        text: Text to synthesize
        voice: Voice to use (None for default)
        rate: Speech rate
        volume: Volume level
        
    Returns:
        WAV audio bytes
    """
    tts = get_tts_instance(voice, rate, volume)
    return tts.synthesize_text(text)

def list_voices() -> list:
    """List available TTS voices."""
    tts = get_tts_instance()
    return tts.get_available_voices()

def initialize_tts(voice: Optional[str] = None, rate: int = 150, volume: float = 0.9) -> None:
    """Initialize TTS engine at startup to eliminate first-request delay."""
    global _tts_instance
    logging.info("[TTS] Initializing TTS engine...")
    with _tts_lock:
        _tts_instance = StreamingTTS(voice, rate, volume)
    
    # Test synthesis to ensure everything works (non-blocking check)
    try:
        test_audio = _tts_instance.synthesize_text("System initialized")
        if test_audio:
            logging.info("[TTS] Test synthesis successful")
        else:
            logging.warning("[TTS] Test synthesis produced no audio")
    except Exception as e:
        logging.warning(f"[TTS] Test synthesis failed: {e}")

def cleanup_tts() -> None:
    """Clean up TTS engine resources."""
    global _tts_instance
    with _tts_lock:
        if _tts_instance and getattr(_tts_instance, "engine", None):
            try:
                _tts_instance.engine.stop()
                logging.info("[TTS] TTS engine stopped")
            except Exception:
                pass
        _tts_instance = None
