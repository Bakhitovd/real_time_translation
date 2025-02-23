import numpy as np
import torch
from faster_whisper import WhisperModel

# Decide which device to use
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Loading Faster Whisper model on {DEVICE}...")

# Load the model (use the appropriate model size; here "small" is used for speed)
model = WhisperModel("small", device=DEVICE, compute_type="int8")
print("ASR model loaded.")

def transcribe(audio_np: np.ndarray) -> str:
    """
    Transcribe a segment of audio (numpy array) using Faster Whisper.
    Assumes the input language is Russian.
    """
    segments, _ = model.transcribe(audio_np, language="ru", beam_size=1)
    transcription = " ".join([seg.text for seg in segments]).strip()
    return transcription
