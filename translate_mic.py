#!/usr/bin/env python3
"""
Continuous microphone capture, transcription, and translation.
This script demonstrates the full pipeline:
1. Capture audio from microphone
2. Transcribe the Russian speech
3. Translate it to English
"""

import sys
import os
import logging
import time
import argparse
import numpy as np
from typing import Optional
import threading
import queue

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add the src directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

# Global variables
audio_queue = queue.Queue()
transcription_queue = queue.Queue()
stop_event = threading.Event()

def audio_capture_thread(device_index: Optional[int] = None, chunk_duration: float = 3.0):
    """Thread for capturing audio from the microphone"""
    try:
        from src import audio_input
        
        logger.info(f"Starting audio capture with device: {device_index if device_index is not None else 'default'}")
        logger.info(f"Chunk duration: {chunk_duration} seconds")
        
        # Set up microphone stream
        mic_stream = audio_input.mic_stream(
            chunk_duration=chunk_duration,
            device_index=device_index,
            noise_reduction=True
        )
        
        # Capture audio chunks until stopped
        for audio_chunk in mic_stream:
            if stop_event.is_set():
                break
                
            # Calculate audio level for display
            level = np.max(np.abs(audio_chunk)) * 100
            
            # Skip if level is too low (silence)
            if level < 3.0:
                continue
                
            # Create a simple audio level meter
            bar_length = int(level / 5)
            bar = '█' * bar_length + '░' * (20 - bar_length)
            logger.info(f"Audio level: {level:.1f}% |{bar}|")
            
            # Add the chunk to the queue for processing
            audio_queue.put(audio_chunk)
            
    except Exception as e:
        logger.error(f"Error in audio capture thread: {str(e)}")
        stop_event.set()

def transcription_thread():
    """Thread for transcribing audio chunks"""
    try:
        from src import asr
        
        logger.info("Starting transcription thread")
        
        while not stop_event.is_set():
            try:
                # Get an audio chunk from the queue (with timeout)
                audio_chunk = audio_queue.get(timeout=1.0)
                
                # Process the audio chunk
                logger.info("Transcribing audio chunk...")
                start_time = time.time()
                
                transcription, confidence = asr.transcribe(audio_chunk)
                
                elapsed_time = time.time() - start_time
                logger.info(f"Transcription completed in {elapsed_time:.2f} seconds (confidence: {confidence:.2f})")
                
                # Check if we got any transcription
                if transcription:
                    logger.info(f"Russian transcription: \"{transcription}\"")
                    
                    # Add to the transcription queue for translation
                    transcription_queue.put(transcription)
                else:
                    logger.info("No transcription returned")
                    
                # Mark the task as done
                audio_queue.task_done()
                
            except queue.Empty:
                # Queue timeout, just continue
                pass
                
    except Exception as e:
        logger.error(f"Error in transcription thread: {str(e)}")
        stop_event.set()

def translation_thread():
    """Thread for translating transcribed text"""
    try:
        from src import translation
        
        logger.info("Starting translation thread")
        
        while not stop_event.is_set():
            try:
                # Get a transcription from the queue (with timeout)
                transcription = transcription_queue.get(timeout=1.0)
                
                # Translate the text
                logger.info("Translating text...")
                start_time = time.time()
                
                translated_text = translation.translate_text(transcription)
                
                elapsed_time = time.time() - start_time
                logger.info(f"Translation completed in {elapsed_time:.2f} seconds")
                
                # Display the translation
                if translated_text:
                    logger.info(f"English translation: \"{translated_text}\"")
                    
                    # Display a separator for readability
                    logger.info("-" * 80)
                else:
                    logger.info("No translation returned")
                    
                # Mark the task as done
                transcription_queue.task_done()
                
            except queue.Empty:
                # Queue timeout, just continue
                pass
                
    except Exception as e:
        logger.error(f"Error in translation thread: {str(e)}")
        stop_event.set()

def main():
    parser = argparse.ArgumentParser(description="Continuous microphone capture, transcription and translation")
    parser.add_argument("--device", type=int, help="PyAudio device index")
    parser.add_argument("--list-devices", action="store_true", help="List available audio devices and exit")
    parser.add_argument("--chunk-duration", type=float, default=3.0, help="Duration of each audio chunk in seconds")
    args = parser.parse_args()
    
    try:
        # Import modules to check they're available
        from src import audio_input, asr, translation
        
        # List audio devices if requested
        if args.list_devices:
            devices = audio_input.list_audio_devices()
            logger.info("Available audio devices:")
            for idx, name in devices:
                logger.info(f"  {idx}: {name}")
            return True
            
        # Start the processing threads
        threads = []
        
        # Audio capture thread
        audio_thread = threading.Thread(
            target=audio_capture_thread,
            args=(args.device, args.chunk_duration),
            daemon=True
        )
        threads.append(audio_thread)
        
        # Transcription thread
        trans_thread = threading.Thread(
            target=transcription_thread,
            daemon=True
        )
        threads.append(trans_thread)
        
        # Translation thread
        tl_thread = threading.Thread(
            target=translation_thread,
            daemon=True
        )
        threads.append(tl_thread)
        
        # Start all threads
        for thread in threads:
            thread.start()
            
        logger.info("All threads started. Press Ctrl+C to stop.")
        
        # Main thread just waits for keyboard interrupt
        try:
            while True:
                time.sleep(0.1)
                
        except KeyboardInterrupt:
            logger.info("Stopping threads...")
            stop_event.set()
            
            # Wait for threads to finish
            for thread in threads:
                thread.join(timeout=2.0)
                
            logger.info("All threads stopped")
            
        return True
        
    except Exception as e:
        logger.error(f"Error in main: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return False

if __name__ == "__main__":
    main()