"""
Utility functions for audio framing, logging, latency measurement, and audio format conversion.
"""

import time
import io

def log_latency(stage: str, duration: float):
    """
    Log the latency for a given processing stage.
    """
    print(f"[{stage}] {duration*1000:.1f} ms")

def log_error(stage: str, error: Exception):
    """
    Log an error for a given processing stage.
    """
    print(f"[ERROR] {stage}: {error}")

def convert_audio_to_wav(audio_bytes: bytes, input_format: str) -> bytes:
    """
    Convert audio bytes from input_format (e.g., 'webm', 'opus') to WAV/PCM bytes using ffmpeg.
    If input_format is already 'wav', returns the input unchanged.
    """
    if input_format == "wav":
        return audio_bytes

    import ffmpeg

    try:
        # Create ffmpeg process to convert audio
        process = (
            ffmpeg
            .input('pipe:0', format=input_format)
            .output('pipe:1', format='wav', acodec='pcm_s16le', ac=1, ar='16k')
            .run_async(pipe_stdin=True, pipe_stdout=True, pipe_stderr=True)
        )
        
        # Send input audio and get converted output
        stdout, stderr = process.communicate(input=audio_bytes)
        
        if process.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown ffmpeg error"
            raise RuntimeError(f"ffmpeg conversion failed: {error_msg}")
        
        return stdout
        
    except Exception as e:
        log_error("convert_audio_to_wav", e)
        raise RuntimeError(f"Audio conversion failed: {e}")
