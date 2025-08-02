"""
Utility functions for audio framing, logging, latency measurement, and audio format conversion.
"""

import time
import io
import logging
import wave
import struct

def log_latency(stage: str, duration: float):
    """
    Log the latency for a given processing stage.
    """
    logging.info(f"[{stage}] {duration*1000:.1f} ms")

def log_error(stage: str, error: Exception):
    """
    Log an error for a given processing stage.
    """
    logging.error(f"[ERROR] {stage}: {error}")

def validate_wav_format(wav_bytes: bytes) -> bool:
    """
    Validate that audio bytes are in proper WAV format.
    Returns True if valid, False otherwise.
    """
    try:
        if len(wav_bytes) < 44:  # Minimum WAV header size
            return False
            
        # Check RIFF header
        if wav_bytes[:4] != b'RIFF':
            return False
            
        # Check WAVE format
        if wav_bytes[8:12] != b'WAVE':
            return False
            
        # Check fmt chunk
        if wav_bytes[12:16] != b'fmt ':
            return False
            
        return True
    except:
        return False

def get_audio_info(audio_bytes: bytes, format_type: str) -> dict:
    """
    Extract audio information for debugging purposes.
    """
    info = {
        "size_bytes": len(audio_bytes),
        "format": format_type
    }
    
    if format_type == "wav" and validate_wav_format(audio_bytes):
        try:
            # Extract WAV format details
            audio_format = struct.unpack('<H', audio_bytes[20:22])[0]
            channels = struct.unpack('<H', audio_bytes[22:24])[0]
            sample_rate = struct.unpack('<I', audio_bytes[24:28])[0]
            bits_per_sample = struct.unpack('<H', audio_bytes[34:36])[0]
            
            info.update({
                "audio_format": audio_format,
                "channels": channels,
                "sample_rate": sample_rate,
                "bits_per_sample": bits_per_sample,
                "valid_wav": True
            })
        except:
            info["valid_wav"] = False
    
    return info

def convert_audio_to_wav(audio_bytes: bytes, input_format: str) -> bytes:
    """
    Convert audio bytes from input_format (e.g., 'webm', 'opus') to WAV/PCM bytes using ffmpeg.
    If input_format is already 'wav', returns the input unchanged.
    Enhanced with validation and detailed error reporting.
    """
    start_time = time.time()
    
    # Log input information  
    input_info = get_audio_info(audio_bytes, input_format)
    logging.info(f"Converting audio: {input_info}")
    
    if input_format == "wav":
        if validate_wav_format(audio_bytes):
            logging.info("Input already in valid WAV format, returning unchanged")
            return audio_bytes
        else:
            logging.warning("Input claims WAV format but validation failed, attempting conversion")

    try:
        import ffmpeg
        
        # Create ffmpeg process to convert audio
        logging.debug("Starting ffmpeg conversion process")
        process = (
            ffmpeg
            .input('pipe:0', format=input_format)
            .output('pipe:1', format='wav', acodec='pcm_s16le', ac=1, ar='16000')
            .overwrite_output()
            .run_async(pipe_stdin=True, pipe_stdout=True, pipe_stderr=True, quiet=True)
        )
        
        # Send input audio and get converted output
        stdout, stderr = process.communicate(input=audio_bytes)
        
        if process.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown ffmpeg error"
            logging.error(f"ffmpeg conversion failed with return code {process.returncode}: {error_msg}")
            raise RuntimeError(f"ffmpeg conversion failed: {error_msg}")
        
        # Validate output
        if not validate_wav_format(stdout):
            logging.error("ffmpeg produced invalid WAV output")
            raise RuntimeError("ffmpeg produced invalid WAV output")
            
        output_info = get_audio_info(stdout, "wav")
        conversion_time = time.time() - start_time
        
        logging.info(f"Audio conversion successful: {output_info}")
        log_latency("audio_conversion", conversion_time)
        
        return stdout
        
    except ImportError:
        logging.error("ffmpeg-python not available for audio conversion")
        raise RuntimeError("ffmpeg-python not available for audio conversion")
    except Exception as e:
        conversion_time = time.time() - start_time
        log_error("convert_audio_to_wav", e)
        log_latency("audio_conversion_failed", conversion_time)
        raise RuntimeError(f"Audio conversion failed: {e}")
