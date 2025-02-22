import threading
import time
from audio_input import start_mic_stream  # Or use stream_from_file("path/to/file.wav")
from asr import asr_loop
from translation import translation_loop
from tts import tts_loop
from mixer import mixer_loop

def main():
    # Start audio input (choose USB mic or file input)
    start_mic_stream()
    # For file input, uncomment:
    # from audio_input import stream_from_file
    # stream_from_file("path/to/audio.wav")
    
    # Start processing threads
    asr_thread = threading.Thread(target=asr_loop, daemon=True)
    translation_thread = threading.Thread(target=translation_loop, daemon=True)
    tts_thread = threading.Thread(target=tts_loop, daemon=True)
    mixer_thread = threading.Thread(target=mixer_loop, daemon=True)
    
    asr_thread.start()
    translation_thread.start()
    tts_thread.start()
    mixer_thread.start()
    
    print("Real-Time Audio Translation Pipeline is running. Press Ctrl+C to exit.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Exiting pipeline...")

if __name__ == '__main__':
    main()
