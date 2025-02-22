import pyaudio
import wave
import threading
import queue

# Global queues for audio data
AUDIO_QUEUE = queue.Queue()           # For ASR processing
ORIGINAL_AUDIO_QUEUE = queue.Queue()    # For playback mixing

CHUNK_SIZE = 1024     # Frames per chunk
RATE = 16000          # Sampling rate (Hz)
CHANNELS = 1          # Mono audio

def start_mic_stream():
    """
    Captures audio from the USB microphone and pushes data into both AUDIO_QUEUE and ORIGINAL_AUDIO_QUEUE.
    """
    p = pyaudio.PyAudio()
    stream = p.open(format=pyaudio.paInt16,
                    channels=CHANNELS,
                    rate=RATE,
                    input=True,
                    frames_per_buffer=CHUNK_SIZE)
    
    def read_mic():
        print("Starting USB microphone stream...")
        while True:
            data = stream.read(CHUNK_SIZE)
            AUDIO_QUEUE.put(data)
            ORIGINAL_AUDIO_QUEUE.put(data)
    
    thread = threading.Thread(target=read_mic, daemon=True)
    thread.start()
    return AUDIO_QUEUE

def stream_from_file(file_path):
    """
    Streams audio from a WAV file, simulating live input.
    """
    wf = wave.open(file_path, 'rb')
    
    def read_file():
        print("Streaming audio from file:", file_path)
        while True:
            data = wf.readframes(CHUNK_SIZE)
            if not data:
                break
            AUDIO_QUEUE.put(data)
            ORIGINAL_AUDIO_QUEUE.put(data)
        wf.close()
        AUDIO_QUEUE.put(None)          # Signal end of stream
        ORIGINAL_AUDIO_QUEUE.put(None)
    
    thread = threading.Thread(target=read_file, daemon=True)
    thread.start()
    return AUDIO_QUEUE