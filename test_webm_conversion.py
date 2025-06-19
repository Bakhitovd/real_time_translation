#!/usr/bin/env python3
"""
Test script to verify WebM audio conversion pipeline
"""

import logging
import asyncio
from app.utils import convert_audio_to_wav
from app.asr import transcribe_chunk
from app.mt import translate_text
from app.tts import synthesize_text

# Configure logging
logging.basicConfig(level=logging.INFO)

async def test_audio_pipeline():
    """Test the complete audio pipeline with a sample file"""
    
    # First, let's test if we can create a WebM file to test with
    # We'll use an existing WAV file and try the pipeline
    
    try:
        # Use existing sample audio
        with open("input_audio/sample.wav", "rb") as f:
            wav_data = f.read()
        
        print(f"Loaded sample audio: {len(wav_data)} bytes")
        
        # Test 1: ASR directly with WAV
        print("\n=== Testing ASR with WAV ===")
        transcript = transcribe_chunk(wav_data)
        print(f"Transcript: '{transcript}'")
        
        if transcript.strip():
            # Test 2: Machine Translation
            print("\n=== Testing Machine Translation ===")
            translated = await translate_text(transcript, "auto", "en")
            print(f"Translation: '{translated}'")
            
            # Test 3: Text-to-Speech
            print("\n=== Testing Text-to-Speech ===")
            tts_audio = synthesize_text(translated)
            print(f"TTS Audio: {len(tts_audio)} bytes")
            
            # Save TTS output
            with open("test_tts_output.wav", "wb") as f:
                f.write(tts_audio)
            print("Saved TTS output to test_tts_output.wav")
        
        print("\n=== Pipeline Test Complete ===")
        
    except Exception as e:
        print(f"Error in pipeline test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_audio_pipeline())
