#!/usr/bin/env python3
"""
Test WebM audio conversion specifically
"""

import subprocess
import logging
from app.utils import convert_audio_to_wav

logging.basicConfig(level=logging.INFO)

def test_webm_conversion():
    """Test WebM to WAV conversion"""
    
    try:
        # First, create a WebM file from our existing WAV sample
        print("=== Creating WebM file for testing ===")
        
        # Convert WAV to WebM using ffmpeg
        result = subprocess.run([
            'ffmpeg', '-i', 'input_audio/sample.wav', 
            '-c:a', 'libopus', '-b:a', '64k',
            'test_sample.webm', '-y'
        ], capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"FFmpeg error: {result.stderr}")
            return
            
        print("Created test_sample.webm")
        
        # Now test our conversion function
        print("\n=== Testing WebM to WAV conversion ===")
        
        with open("test_sample.webm", "rb") as f:
            webm_data = f.read()
            
        print(f"WebM input: {len(webm_data)} bytes")
        
        # Convert WebM to WAV
        wav_data = convert_audio_to_wav(webm_data, input_format="webm")
        print(f"WAV output: {len(wav_data)} bytes")
        
        # Save converted WAV
        with open("test_converted.wav", "wb") as f:
            f.write(wav_data)
        print("Saved converted WAV to test_converted.wav")
        
        print("\n=== WebM conversion test successful! ===")
        
    except Exception as e:
        print(f"Error in WebM conversion test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_webm_conversion()
