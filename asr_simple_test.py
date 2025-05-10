#!/usr/bin/env python3
"""
Simple test for the ASR module.
Validates that the module can load and transcribe audio from a file.
"""

import sys
import os
import logging
import numpy as np
import soundfile as sf

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add the src directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

def main():
    # Path to test audio file
    audio_file = "speech_ru.mp3"
    
    if not os.path.exists(audio_file):
        logger.error(f"Audio file not found: {audio_file}")
        return False
    
    logger.info(f"Testing ASR module with audio file: {audio_file}")
    
    try:
        # Import the ASR module
        from src import asr
        logger.info("ASR module imported successfully")
        
        # Load the audio file
        logger.info(f"Loading audio from {audio_file}")
        audio_data, sample_rate = sf.read(audio_file)
        
        # Convert to mono if stereo
        #if len(audio_data.shape) > 1 and audio_data.shape[1] > 1:
        #    audio_data = audio_data.mean(axis=1)
        #
        ## Normalize audio
        #if audio_data.dtype != np.float32:
        #    audio_data = audio_data.astype(np.float32)
        #if np.max(np.abs(audio_data)) > 1.0:
        #    audio_data = audio_data / np.max(np.abs(audio_data))
        
        # Transcribe audio
        logger.info("Transcribing audio...")
        transcription, confidence = asr.transcribe(audio_data, language="ru")
        
        # Display results
        logger.info(f"Confidence score: {confidence:.4f}")
        if transcription:
            logger.info(f"Transcription: \"{transcription}\"")
            return True
        else:
            logger.warning("No transcription returned")
            return False
            
    except Exception as e:
        logger.error(f"Error testing ASR module: {str(e)}")
        return False

if __name__ == "__main__":
    main()