"""
Test script for Text-to-Speech (TTS) using pyttsx3.
Usage:
    python scripts/test_tts.py "Text to synthesize" [--lang en|ru] [--output filename.wav]
"""

import sys
import os

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.tts import synthesize_text

def usage():
    print("Usage: python scripts/test_tts.py \"Text to synthesize\" [--lang en|ru] [--output filename.wav]")
    print("Example: python scripts/test_tts.py \"Hello world\" --output test_output.wav")
    sys.exit(1)

def main():
    if len(sys.argv) < 2:
        usage()

    text = sys.argv[1]
    output_file = "test_tts_output.wav"
    language = "en"

    # Parse optional arguments
    i = 2
    while i < len(sys.argv):
        if sys.argv[i] == "--output" and i + 1 < len(sys.argv):
            output_file = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--lang" and i + 1 < len(sys.argv):
            language = sys.argv[i + 1]
            i += 2
        else:
            i += 1

    print(f"Synthesizing text: '{text}'")
    print(f"Language: {language}")
    print(f"Output file: {output_file}")
    print("Processing...")
    
    try:
        # Synthesize text to audio bytes
        audio_bytes = synthesize_text(text)
        
        if audio_bytes:
            # Save to file
            with open(output_file, "wb") as f:
                f.write(audio_bytes)
            
            print(f"✓ TTS completed successfully!")
            print(f"  Generated {len(audio_bytes)} bytes of audio")
            print(f"  Saved to: {output_file}")
            return 0
        else:
            print("✗ TTS failed - no audio generated")
            return 1
            
    except Exception as e:
        print(f"✗ TTS error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
