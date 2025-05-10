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
import colorama
from colorama import Fore, Back, Style

# Initialize colorama
colorama.init()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add the src directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

# Global variables
audio_queue = queue.Queue()
transcription_queue = queue.Queue()
stop_event = threading.Event()

# For quiet mode display
quiet_mode = False

def print_quiet_mode(russian_text, english_text, audio_level=None, error=None):
    """Display translation information in a clean, colorful format for quiet mode"""
    if not quiet_mode:
        return

    # Clear line and move to start
    sys.stdout.write('\r' + ' ' * 100 + '\r')

    if error:
        # Print error message
        sys.stdout.write(f"{Fore.RED}Error: {error}{Style.RESET_ALL}\n")
    elif audio_level is not None:
        # Print audio level meter
        bar_length = int(audio_level / 5)
        level_bar = '█' * bar_length + '░' * (20 - bar_length)
        sys.stdout.write(f"{Fore.CYAN}Audio: {audio_level:4.1f}% |{level_bar}|{Style.RESET_ALL}\n")
    elif russian_text and english_text:
        # Print transcription and translation
        sys.stdout.write(f"{Fore.YELLOW}Russian: {russian_text}{Style.RESET_ALL}\n")
        sys.stdout.write(f"{Fore.GREEN}English: {english_text}{Style.RESET_ALL}\n")
        sys.stdout.write(f"{Fore.BLUE}{'-' * 50}{Style.RESET_ALL}\n")

    sys.stdout.flush()

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

            # Display audio level
            if quiet_mode:
                print_quiet_mode(None, None, audio_level=level)
            else:
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
                    if not quiet_mode:
                        logger.info(f"Russian transcription: \"{transcription}\"")

                    # Add to the transcription queue for translation
                    transcription_queue.put(transcription)
                else:
                    if quiet_mode:
                        print_quiet_mode(None, None, error="No transcription returned")
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
                    if quiet_mode:
                        print_quiet_mode(transcription, translated_text)
                    else:
                        logger.info(f"English translation: \"{translated_text}\"")
                        # Display a separator for readability
                        logger.info("-" * 80)
                else:
                    if quiet_mode:
                        print_quiet_mode(None, None, error="No translation returned")
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
    parser.add_argument("--quiet", "-q", action="store_true", help="Quiet mode - show only translations without technical details")
    parser.add_argument("--debug", "-d", action="store_true", help="Debug mode - show verbose logging")
    args = parser.parse_args()

    # Set logging level based on arguments
    global quiet_mode
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    elif args.quiet:
        quiet_mode = True
        logging.getLogger().setLevel(logging.ERROR)  # Only show errors
        print(f"{Fore.CYAN}Starting in quiet mode. Press Ctrl+C to stop.{Style.RESET_ALL}")
        print(f"{Fore.CYAN}Loading models, please wait...{Style.RESET_ALL}")
    
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
            if quiet_mode:
                print(f"\n{Fore.CYAN}Stopping translation...{Style.RESET_ALL}")
            else:
                logger.info("Stopping threads...")

            stop_event.set()

            # Wait for threads to finish
            for thread in threads:
                thread.join(timeout=2.0)

            if quiet_mode:
                print(f"{Fore.CYAN}Translation stopped.{Style.RESET_ALL}")
            else:
                logger.info("All threads stopped")
            
        return True
        
    except Exception as e:
        logger.error(f"Error in main: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return False

if __name__ == "__main__":
    main()