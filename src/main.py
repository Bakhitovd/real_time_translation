#!/usr/bin/env python3
"""
Main application for Real-Time Audio Translation
Integrates all components:
1. Audio Input - Capture from microphone
2. ASR - Transcribe Russian speech
3. Translation - Translate to English
4. Caption Display - Show translations
"""

import sys
import os
import logging
import time
import argparse
import threading
import queue
import numpy as np
from typing import Optional

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import project modules
from audio_input import mic_stream
from asr import transcribe
from translation import translate_text
from caption_ui import CaptionDisplayUI

# Global variables
audio_queue = queue.Queue()
transcription_queue = queue.Queue()
stop_event = threading.Event()

def audio_capture_thread(device_index: Optional[int] = None, chunk_duration: float = 3.0):
    """Thread for capturing audio from the microphone"""
    try:
        logger.info(f"Starting audio capture with device: {device_index if device_index is not None else 'default'}")
        logger.info(f"Chunk duration: {chunk_duration} seconds")
        
        # Set up microphone stream
        mic = mic_stream(
            chunk_duration=chunk_duration,
            device_index=device_index,
            noise_reduction=True
        )
        
        # Capture audio chunks until stopped
        for audio_chunk in mic:
            if stop_event.is_set():
                break
                
            # Calculate audio level for display
            level = np.max(np.abs(audio_chunk)) * 100
            
            # Skip if level is too low (silence)
            if level < 3.0:
                continue
            
            # Update audio level in UI
            if ui:
                ui.update_audio_level(level)
            
            # Add the chunk to the queue for processing
            audio_queue.put(audio_chunk)
            
    except Exception as e:
        logger.error(f"Error in audio capture thread: {str(e)}")
        if ui:
            ui.show_error(f"Audio capture error: {str(e)}")
        stop_event.set()

def transcription_thread():
    """Thread for transcribing audio chunks"""
    try:
        logger.info("Starting transcription thread")
        
        while not stop_event.is_set():
            try:
                # Get an audio chunk from the queue (with timeout)
                audio_chunk = audio_queue.get(timeout=1.0)
                
                # Process the audio chunk
                logger.info("Transcribing audio chunk...")
                ui.update_status("Transcribing audio...") if ui else None
                
                start_time = time.time()
                transcription, confidence = transcribe(audio_chunk)
                
                elapsed_time = time.time() - start_time
                logger.info(f"Transcription completed in {elapsed_time:.2f} seconds (confidence: {confidence:.2f})")
                
                # Check if we got any transcription
                if transcription:
                    logger.info(f"Russian transcription: \"{transcription}\"")
                    
                    # Add to the transcription queue for translation
                    transcription_queue.put(transcription)
                else:
                    logger.info("No transcription returned")
                    if ui:
                        ui.update_status("No speech detected")
                    
                # Mark the task as done
                audio_queue.task_done()
                
            except queue.Empty:
                # Queue timeout, just continue
                pass
                
    except Exception as e:
        logger.error(f"Error in transcription thread: {str(e)}")
        if ui:
            ui.show_error(f"Transcription error: {str(e)}")
        stop_event.set()

def translation_thread():
    """Thread for translating transcribed text"""
    try:
        logger.info("Starting translation thread")
        
        while not stop_event.is_set():
            try:
                # Get a transcription from the queue (with timeout)
                transcription = transcription_queue.get(timeout=1.0)
                
                # Translate the text
                logger.info("Translating text...")
                ui.update_status("Translating...") if ui else None
                
                start_time = time.time()
                translated_text = translate_text(transcription)
                
                elapsed_time = time.time() - start_time
                logger.info(f"Translation completed in {elapsed_time:.2f} seconds")
                
                # Display the translation
                if translated_text:
                    logger.info(f"English translation: \"{translated_text}\"")
                    
                    # Update UI with new translation
                    if ui:
                        ui.display_translation(transcription, translated_text)
                        ui.update_status("Ready")
                else:
                    logger.info("No translation returned")
                    if ui:
                        ui.update_status("Translation failed")
                    
                # Mark the task as done
                transcription_queue.task_done()
                
            except queue.Empty:
                # Queue timeout, just continue
                pass
                
    except Exception as e:
        logger.error(f"Error in translation thread: {str(e)}")
        if ui:
            ui.show_error(f"Translation error: {str(e)}")
        stop_event.set()

def on_ui_close():
    """Handle UI window closure"""
    logger.info("UI window closed. Stopping threads...")
    stop_event.set()

def main():
    parser = argparse.ArgumentParser(description="Real-Time Audio Translation with Caption Display")
    parser.add_argument("--device", type=int, help="PyAudio device index")
    parser.add_argument("--list-devices", action="store_true", help="List available audio devices and exit")
    parser.add_argument("--chunk-duration", type=float, default=3.0, help="Duration of each audio chunk in seconds")
    parser.add_argument("--debug", "-d", action="store_true", help="Debug mode - show verbose logging")
    parser.add_argument("--console-only", "-c", action="store_true", help="Run in console-only mode without GUI")
    parser.add_argument("--theme", type=str, default="default", choices=["default", "dark", "light"], help="UI theme (default, dark, light)")
    parser.add_argument("--hide-russian", action="store_true", help="Hide the original Russian text in the UI")
    args = parser.parse_args()

    # Set logging level based on arguments
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    try:
        # Import audio_input module to access list_audio_devices
        from audio_input import list_audio_devices
        
        # List audio devices if requested
        if args.list_devices:
            devices = list_audio_devices()
            logger.info("Available audio devices:")
            for idx, name in devices:
                logger.info(f"  {idx}: {name}")
            return True
        
        # Decide whether to use GUI or console mode
        global ui
        ui = None

        if not args.console_only:
            # Check if Tkinter is available
            try:
                import tkinter
                # Create the Caption UI
                ui = CaptionDisplayUI(
                    title="Real-Time Translation",
                    show_russian=not args.hide_russian,
                    theme=args.theme
                )
                ui.set_close_callback(on_ui_close)
                ui.update_status("Starting up...")
            except ImportError:
                logger.error("Tkinter is not available - falling back to console mode")
                logger.error("To use the GUI, install Tkinter (python3-tk) on your system")
        
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
            
        logger.info("All threads started.")
        if ui:
            ui.update_status("Ready - Listening for speech...")
        else:
            logger.info("Running in console-only mode. Press Ctrl+C to stop.")
        
        # Main thread handles UI or waits for keyboard interrupt
        try:
            if ui and not args.console_only:
                # If we have a UI, run it in the main thread
                logger.info("Starting UI in main thread. Close the window to stop.")
                ui.start()  # This will block until window is closed
                stop_event.set()  # Window closed, stop everything
            else:
                # No UI, just wait for keyboard interrupt
                logger.info("Running in console-only mode. Press Ctrl+C to stop.")
                while not stop_event.is_set():
                    time.sleep(0.1)

        except KeyboardInterrupt:
            logger.info("Stopping application...")
            stop_event.set()

        # Wait for threads to finish
        for thread in threads:
            thread.join(timeout=2.0)
            
        logger.info("Application stopped")
        return True
        
    except Exception as e:
        logger.error(f"Error in main: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return False

if __name__ == "__main__":
    main()