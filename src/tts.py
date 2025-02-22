import queue
from TTS.api import TTS
from translation import TTS_QUEUE

# Queue for passing synthesized TTS audio (numpy arrays) to the mixer
TTS_AUDIO_QUEUE = queue.Queue()

# Initialize TTS model (adjust model as desired)
tts_model = TTS(model_name="tts_models/en/ljspeech/tacotron2-DDC", gpu=True)

def synthesize_speech(english_text):
    """
    Converts English text to a waveform (numpy array).
    """
    wav = tts_model.tts(english_text)
    return wav

def tts_loop():
    """
    Reads translated English text from TTS_QUEUE, synthesizes speech,
    and sends the audio waveform to TTS_AUDIO_QUEUE.
    """
    while True:
        english_text = TTS_QUEUE.get()
        if english_text is None:
            break
        print("Synthesizing speech for:", english_text)
        audio_wav = synthesize_speech(english_text)
        TTS_AUDIO_QUEUE.put(audio_wav)
