import pyaudio
import numpy as np
import time
import logging
import noisereduce as nr

# === Audio Configuration ===
RATE = 16000            # Sampling rate (Hz)
CHANNELS = 1            # Mono audio
FORMAT = pyaudio.paInt16  # 16-bit audio
CHUNK_SIZE = 1024       # Buffer size for PyAudio
BYTES_PER_SAMPLE = 2    # 16-bit audio = 2 bytes per sample

# Default microphone settings
DEFAULT_DEVICE_INDEX = None  # None = use system default

# Logging
logger = logging.getLogger(__name__)

def list_audio_devices():
    """
    Lists all available audio input devices with their indices.
    
    Returns:
        List of (index, name) tuples for available input devices
    """
    p = pyaudio.PyAudio()
    device_list = []
    
    try:
        for i in range(p.get_device_count()):
            device_info = p.get_device_info_by_index(i)
            if device_info.get('maxInputChannels') > 0:  # Input device
                device_list.append((i, device_info.get('name')))
                logger.info(f"Device {i}: {device_info.get('name')}")
    finally:
        p.terminate()
        
    return device_list

def mic_stream(chunk_duration=3, device_index=None, noise_reduction=False):
    """
    Creates a generator that yields audio segments from the microphone.
    
    Args:
        chunk_duration: Duration in seconds for each audio segment
        device_index: PyAudio device index (None for default)
        noise_reduction: Whether to apply noise reduction
        
    Yields:
        numpy.ndarray: Audio segment as normalized float32 array in range [-1.0, 1.0]
    """
    p = pyaudio.PyAudio()
    
    # Calculate frames per buffer based on chunk duration
    frames_per_buffer = CHUNK_SIZE
    chunk_samples = int(RATE * chunk_duration)
    
    # Open microphone stream
    stream = p.open(
        format=FORMAT,
        channels=CHANNELS,
        rate=RATE,
        input=True,
        input_device_index=device_index,
        frames_per_buffer=frames_per_buffer
    )
    
    logger.info(f"Microphone stream opened with device index: {device_index if device_index is not None else 'default'}")
    logger.info(f"Capturing {chunk_duration}s segments at {RATE}Hz")
    
    # Audio buffer for collecting chunks
    audio_buffer = np.array([], dtype=np.int16)
    
    try:
        while True:
            # Read audio chunk from microphone
            data = stream.read(frames_per_buffer)
            
            # Convert to numpy array and append to buffer
            chunk = np.frombuffer(data, dtype=np.int16)
            audio_buffer = np.append(audio_buffer, chunk)
            
            # When we have enough samples for one chunk_duration, process and yield
            if len(audio_buffer) >= chunk_samples:
                # Extract chunk_duration worth of samples
                segment = audio_buffer[:chunk_samples]
                audio_buffer = audio_buffer[chunk_samples:]
                
                # Monitor audio levels
                max_level = get_audio_level(segment)
                
                # Normalize to float32 in range [-1.0, 1.0]
                audio_float = segment.astype(np.float32) / 32768.0
                
                # Apply noise reduction if requested
                if noise_reduction:
                    audio_float = apply_noise_reduction(audio_float)
                    
                yield audio_float
                
    except KeyboardInterrupt:
        logger.info("Microphone stream interrupted")
    except Exception as e:
        logger.error(f"Error in microphone stream: {e}")
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()
        logger.info("Microphone stream closed")

def get_audio_level(audio_data):
    """
    Calculates the audio level (max absolute amplitude) from raw audio data
    
    Args:
        audio_data: Raw audio as numpy array
        
    Returns:
        float: Audio level as percentage (0-100)
    """
    if len(audio_data) == 0:
        return 0
        
    # Calculate max level as percentage of maximum possible value
    max_amplitude = np.max(np.abs(audio_data))
    level_pct = (max_amplitude / 32768.0) * 100
    
    return level_pct

def apply_noise_reduction(audio_float):
    """
    Applies noise reduction to the audio signal
    
    Args:
        audio_float: Normalized float audio data in range [-1.0, 1.0]
        
    Returns:
        numpy.ndarray: Noise-reduced audio data
    """
    # Use stationary noise reduction
    # The first 0.5 seconds are assumed to be noise
    noise_sample_count = int(RATE * 0.5)
    if len(audio_float) > noise_sample_count:
        noise_sample = audio_float[:noise_sample_count]
        reduced = nr.reduce_noise(
            y=audio_float,
            y_noise=noise_sample,
            sr=RATE,
            stationary=True
        )
        return reduced
    else:
        return audio_float