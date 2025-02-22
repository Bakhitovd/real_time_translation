import numpy as np
import sounddevice as sd
from audio_input import ORIGINAL_AUDIO_QUEUE
from tts import TTS_AUDIO_QUEUE

def mix_audio(original_chunk, tts_chunk, original_volume=0.3):
    """
    Mixes two audio signals:
    - original_chunk: raw PCM bytes (int16) from the original audio.
    - tts_chunk: a numpy array (float32) from the TTS engine.
    Returns a mixed numpy array (float32) normalized between -1 and 1.
    """
    # Convert original audio bytes to numpy float32 array
    original_np = np.frombuffer(original_chunk, dtype=np.int16).astype(np.float32) / 32768.0
    len_original = len(original_np)
    len_tts = len(tts_chunk)
    mixed_len = max(len_original, len_tts)
    mixed = np.zeros(mixed_len, dtype=np.float32)
    
    if len_original > 0:
        mixed[:len_original] += original_np * original_volume
    if len_tts > 0:
        mixed[:len_tts] += tts_chunk
    return np.clip(mixed, -1.0, 1.0)

def mixer_loop():
    """
    Waits for TTS audio and then gathers a corresponding segment of original audio.
    Mixes them and plays the result.
    """
    while True:
        tts_audio = TTS_AUDIO_QUEUE.get()
        if tts_audio is None:
            break
        original_chunks = []
        # Estimate the number of samples needed from the original audio to match TTS length.
        tts_length = len(tts_audio)
        collected = 0
        while collected < tts_length:
            original_chunk = ORIGINAL_AUDIO_QUEUE.get()
            if original_chunk is None:
                break
            original_chunks.append(original_chunk)
            # int16: 2 bytes per sample
            collected += len(original_chunk) // 2
        if original_chunks:
            original_data = b"".join(original_chunks)
            mixed = mix_audio(original_data, tts_audio)
            # Assumed playback sample rate (adjust if needed)
            sd.play(mixed, samplerate=22050)
            sd.wait()
        else:
            sd.play(tts_audio, samplerate=22050)
            sd.wait()
