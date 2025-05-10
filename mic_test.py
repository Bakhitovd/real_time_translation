#!/usr/bin/env python3
"""
Test script for capturing audio from microphone and transcribing it.
This tests both the audio input module and ASR module together.
"""

import sys
import os
import logging
import time
import argparse
import numpy as np

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add the src directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

def main():
    parser = argparse.ArgumentParser(description="Test microphone capture and transcription")
    parser.add_argument("--duration", type=int, default=5, help="Duration to record in seconds")
    parser.add_argument("--device", type=int, help="PyAudio device index")
    parser.add_argument("--list-devices", action="store_true", help="List available audio devices")
    parser.add_argument("--continuous", action="store_true", help="Run in continuous mode")
    args = parser.parse_args()
    
    try:
        # Import modules
        from src import audio_input, asr
        logger.info("Modules imported successfully")
        
        # List audio devices if requested
        if args.list_devices:
            devices = audio_input.list_audio_devices()
            logger.info("Available audio devices:")
            for idx, name in devices:
                logger.info(f"  {idx}: {name}")
            return True
        
        if args.continuous:
            # Continuous mode - keep capturing and transcribing
            logger.info(f"Starting continuous capture with device: {args.device if args.device is not None else 'default'}")
            logger.info("Press Ctrl+C to stop")
            
            # Set up microphone stream with 3-second chunks
            mic_stream = audio_input.mic_stream(
                chunk_duration=3,
                device_index=args.device,
                noise_reduction=True
            )
            
            try:
                for audio_chunk in mic_stream:
                    # Calculate audio level for display
                    level = np.max(np.abs(audio_chunk)) * 100
                    bar_length = int(level / 5)
                    bar = '█' * bar_length + '░' * (20 - bar_length)
                    logger.info(f"Audio level: {level:.1f}% |{bar}|")
                    
                    # Skip transcription if audio level is too low (silence)
                    if level < 2.0:
                        logger.info("Audio level too low, skipping transcription")
                        continue
                    
                    # Transcribe the audio chunk
                    logger.info("Transcribing...")
                    start_time = time.time()
                    
                    transcription, confidence = asr.transcribe(audio_chunk)
                    
                    elapsed_time = time.time() - start_time
                    logger.info(f"Transcription completed in {elapsed_time:.2f} seconds")
                    logger.info(f"Confidence: {confidence:.4f}")
                    
                    if transcription:
                        logger.info(f"Transcription: \"{transcription}\"")
                    else:
                        logger.info("No transcription returned")
                        
            except KeyboardInterrupt:
                logger.info("Stopped by user")
            
        else:
            # Single capture mode
            logger.info(f"Recording for {args.duration} seconds with device: {args.device if args.device is not None else 'default'}")
            
            # Start recording
            audio_data = capture_audio(args.duration, args.device)
            
            # Transcribe the captured audio
            logger.info("Transcribing captured audio...")
            start_time = time.time()
            
            transcription, confidence = asr.transcribe(audio_data)
            
            elapsed_time = time.time() - start_time
            logger.info(f"Transcription completed in {elapsed_time:.2f} seconds")
            logger.info(f"Confidence: {confidence:.4f}")
            
            if transcription:
                logger.info(f"Transcription: \"{transcription}\"")
                return True
            else:
                logger.warning("No transcription returned")
                return False
        
        return True
        
    except Exception as e:
        logger.error(f"Error in microphone test: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return False

def capture_audio(duration, device_index=None):
    """Capture audio for the specified duration"""
    from src import audio_input
    import numpy as np
    
    logger.info(f"Capturing audio for {duration} seconds...")
    
    # Set up variables
    audio_buffer = np.array([], dtype=np.float32)
    start_time = time.time()
    
    # Set up microphone stream with short chunks for responsiveness
    mic_stream = audio_input.mic_stream(
        chunk_duration=0.5,  # Use smaller chunks for more responsive feedback
        device_index=device_index,
        noise_reduction=True
    )
    
    # Capture until we reach the desired duration
    try:
        for audio_chunk in mic_stream:
            # Add the chunk to our buffer
            audio_buffer = np.append(audio_buffer, audio_chunk)
            
            # Calculate and display the audio level
            level = np.max(np.abs(audio_chunk)) * 100
            elapsed = time.time() - start_time
            remaining = max(0, duration - elapsed)
            
            # Create a simple audio level meter
            bar_length = int(level / 5)
            bar = '█' * bar_length + '░' * (20 - bar_length)
            
            logger.info(f"Recording: {elapsed:.1f}s / {duration}s | Level: {level:.1f}% |{bar}| (Remaining: {remaining:.1f}s)")
            
            # Stop if we've recorded for the desired duration
            if elapsed >= duration:
                break
                
    except KeyboardInterrupt:
        logger.info("Recording stopped by user")
    
    logger.info(f"Captured {len(audio_buffer)} samples")
    return audio_buffer

if __name__ == "__main__":
    main()