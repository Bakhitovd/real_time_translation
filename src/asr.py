import queue
import numpy as np
from audio_input import AUDIO_QUEUE
from faster_whisper import WhisperModel

# Queue for passing ASR output (Russian text) to the translation module
TRANSLATION_QUEUE = queue.Queue()

# Initialize Faster Whisper model (adjust model size as needed)
model = WhisperModel("large-v2", device="cuda", compute_type="float16")

def asr_loop():
    """
    Continuously reads audio data from AUDIO_QUEUE, processes chunks for transcription,
    and sends the recognized Russian text to TRANSLATION_QUEUE.
    """
    audio_buffer = b""
    # Threshold: roughly 2 seconds of audio (16k samples, 2 bytes per sample)
    CHUNK_THRESHOLD = RATE * 2 * 2  # RATE defined in audio_input.py
    
    while True:
        data = AUDIO_QUEUE.get()
        if data is None:
            break
        audio_buffer += data
        if len(audio_buffer) >= CHUNK_THRESHOLD:
            # Convert buffer (bytes) to a numpy array of float32 normalized between -1 and 1
            audio_np = np.frombuffer(audio_buffer, np.int16).astype(np.float32) / 32768.0
            segments, _ = model.transcribe(audio_np, language="ru", beam_size=1)
            text = " ".join([seg.text for seg in segments]).strip()
            if text:
                print("ASR output:", text)
                TRANSLATION_QUEUE.put(text)
            audio_buffer = b""
