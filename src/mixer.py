import numpy as np
import soundfile as sf

RATE = 16000

def mix_audio(input_audio: np.ndarray, tts_audio: np.ndarray) -> np.ndarray:
    """
    Mixes the input (denoised) audio with the synthesized TTS audio.
    - If both channels are available, mix using 30% input and 70% TTS.
    - If one channel is empty, return the nonempty one.
    - If both are empty, return an empty array.
    The mixed length is the minimum length of the two non-empty inputs.
    """
    # Ensure inputs are numpy arrays with float32 dtype.
    input_audio = np.asarray(input_audio, dtype=np.float32)
    tts_audio = np.asarray(tts_audio, dtype=np.float32)
    
    # Check for empty inputs
    if input_audio.size == 0 and tts_audio.size == 0:
        return np.array([], dtype=np.float32)
    elif input_audio.size == 0:
        return tts_audio  # Return TTS audio if input is empty.
    elif tts_audio.size == 0:
        return input_audio  # Return input audio if TTS is empty.
    else:
        min_len = min(len(input_audio), len(tts_audio))
        mixed = input_audio[:min_len] * 0.3 + tts_audio[:min_len] * 0.7
        return np.clip(mixed, -1.0, 1.0)

def save_mixed_audio(mixed_audio: np.ndarray, filename: str):
    """
    Save the mixed audio to a WAV file.
    """
    sf.write(filename, mixed_audio, RATE)
