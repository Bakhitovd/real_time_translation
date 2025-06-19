"""
Test script for ASR (Automatic Speech Recognition) using faster-whisper.
Usage:
    python scripts/test_asr.py path/to/audio.wav [--lang en|ru|auto]
"""

import sys
import os

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.asr import transcribe_chunk

def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/test_asr.py path/to/audio.wav [--lang en|ru|auto]")
        sys.exit(1)

    audio_path = sys.argv[1]
    language = None
    if len(sys.argv) > 3 and sys.argv[2] == "--lang":
        language = sys.argv[3]
        if language == "auto":
            language = None

    with open(audio_path, "rb") as f:
        audio_bytes = f.read()

    print(f"Transcribing {audio_path} (language: {language or 'auto'}) ...")
    transcript = transcribe_chunk(audio_bytes, language=language)
    print("Transcript:")
    print(transcript)

if __name__ == "__main__":
    main()
