import numpy as np
from kokoro import KPipeline

# Initialize the Kokoro pipeline.
# Adjust lang_code and voice as needed (here 'a' indicates American English).
pipeline = KPipeline(lang_code='a')

def synthesize_tts(english_text: str) -> np.ndarray:
    """
    Synthesize English speech from text using the Kokoro TTS pipeline.
    The pipeline returns a generator yielding (graphemes, phonemes, audio).
    We'll take the first audio chunk produced.
    """
    generator = pipeline(english_text, voice='af_heart', speed=1, split_pattern=r'\n+')
    try:
        gs, ps, audio = next(generator)
    except StopIteration:
        audio = np.array([])
    return audio
