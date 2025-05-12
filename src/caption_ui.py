"""
Caption Display UI for Real-Time Audio Translation
This module provides a simple UI for displaying translated captions.
It can be used as a standalone window or integrated with the main application.
"""

import tkinter as tk
from tkinter import ttk
import threading
import queue
import time
import sys
from typing import Optional, List, Dict, Any, Callable
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class CaptionDisplayUI:
    """
    A simple UI for displaying translated captions using Tkinter.
    
    Features:
    - Display Russian original text and English translation
    - Support for themes/styling
    - Visual audio level indicator
    - Option to show/hide Russian text
    - Resizable and configurable window
    """
    
    def __init__(
        self,
        title: str = "Real-Time Translation",
        width: int = 800,
        height: int = 300,
        show_russian: bool = True,
        theme: str = "default",
        update_interval: int = 100,  # ms
    ):
        """
        Initialize the Caption Display UI
        
        Args:
            title: Window title
            width: Initial window width
            height: Initial window height
            show_russian: Whether to show the original Russian text
            theme: UI theme ('default', 'dark', 'light')
            update_interval: UI update interval in milliseconds
        """
        self.width = width
        self.height = height
        self.show_russian = show_russian
        self.theme = theme
        self.update_interval = update_interval
        
        # Create message queue for thread-safe updates
        self.message_queue = queue.Queue()
        
        # Setup main window
        self.root = tk.Tk()
        self.root.title(title)
        self.root.geometry(f"{width}x{height}")
        self.root.minsize(400, 200)
        
        # Configure theme
        self._setup_theme(theme)
        
        # Create UI elements
        self._create_widgets()
        
        # Setup closing handler
        self.is_running = False
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        
        # Callback for external stop
        self.on_close_callback = None
    
    def _setup_theme(self, theme: str):
        """Configure colors and styling based on theme"""
        if theme.lower() == "dark":
            self.bg_color = "#2d2d2d"
            self.text_color = "#ffffff"
            self.russian_text_color = "#ffcc00"  # Yellow
            self.english_text_color = "#66ff66"  # Green
            self.status_bg_color = "#1a1a1a"
            self.status_text_color = "#00ccff"  # Cyan
        elif theme.lower() == "light":
            self.bg_color = "#f0f0f0"
            self.text_color = "#333333"
            self.russian_text_color = "#996600"  # Dark yellow
            self.english_text_color = "#006600"  # Dark green
            self.status_bg_color = "#e0e0e0"
            self.status_text_color = "#0066cc"  # Blue
        else:  # default
            self.bg_color = "#3a3a3a"
            self.text_color = "#f0f0f0"
            self.russian_text_color = "#ffcc00"  # Yellow
            self.english_text_color = "#66ff66"  # Green
            self.status_bg_color = "#2a2a2a"
            self.status_text_color = "#00ccff"  # Cyan
        
        self.root.configure(bg=self.bg_color)
        
        # Configure style for ttk widgets
        self.style = ttk.Style()
        self.style.configure(
            "Caption.TLabel",
            background=self.bg_color,
            foreground=self.text_color,
            font=("Helvetica", 12),
            padding=10
        )
        self.style.configure(
            "Russian.TLabel",
            background=self.bg_color,
            foreground=self.russian_text_color,
            font=("Helvetica", 12),
            padding=10
        )
        self.style.configure(
            "English.TLabel",
            background=self.bg_color,
            foreground=self.english_text_color,
            font=("Helvetica", 14, "bold"),
            padding=10
        )
        self.style.configure(
            "Status.TLabel",
            background=self.status_bg_color,
            foreground=self.status_text_color,
            font=("Helvetica", 10),
            padding=5
        )
        self.style.configure(
            "AudioMeter.Horizontal.TProgressbar",
            background=self.status_text_color,
            troughcolor=self.status_bg_color
        )
    
    def _create_widgets(self):
        """Create all UI widgets"""
        # Main frame
        self.main_frame = ttk.Frame(self.root, padding="10")
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Russian text section (optional)
        if self.show_russian:
            self.russian_label = ttk.Label(
                self.main_frame,
                text="Waiting for Russian speech...",
                style="Russian.TLabel",
                wraplength=self.width - 40,
                anchor="w",
                justify="left"
            )
            self.russian_label.pack(fill=tk.X, expand=False)
            
            # Separator
            ttk.Separator(self.main_frame, orient="horizontal").pack(fill=tk.X, pady=5)
        
        # English translation section (main display)
        self.english_label = ttk.Label(
            self.main_frame,
            text="Waiting for translation...",
            style="English.TLabel",
            wraplength=self.width - 40,
            anchor="w",
            justify="left"
        )
        self.english_label.pack(fill=tk.BOTH, expand=True)
        
        # Status bar at the bottom
        self.status_frame = ttk.Frame(self.root)
        self.status_frame.pack(fill=tk.X, side=tk.BOTTOM)
        
        # Audio level indicator
        self.audio_frame = ttk.Frame(self.status_frame)
        self.audio_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, pady=2)
        
        self.audio_level_label = ttk.Label(
            self.audio_frame,
            text="Audio: 0.0%",
            style="Status.TLabel"
        )
        self.audio_level_label.pack(side=tk.LEFT, padx=5)
        
        self.audio_meter = ttk.Progressbar(
            self.audio_frame,
            orient="horizontal",
            mode="determinate",
            style="AudioMeter.Horizontal.TProgressbar",
            length=200
        )
        self.audio_meter.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        # Status info
        self.status_label = ttk.Label(
            self.status_frame,
            text="Ready",
            style="Status.TLabel"
        )
        self.status_label.pack(side=tk.RIGHT, padx=5)
    
    def start(self):
        """Start the UI main loop"""
        if self.is_running:
            return

        self.is_running = True

        # Start the update timer
        self._schedule_update()

        # Run the main loop - only call this from the main thread!
        if threading.current_thread() is threading.main_thread():
            self.root.mainloop()
        else:
            # If running in a thread, just mark as running but don't call mainloop
            logger.warning("UI.start() called from a non-main thread - mainloop not started")
    
    def _schedule_update(self):
        """Schedule periodic UI updates"""
        if self.is_running:
            # Process any pending messages
            self._process_message_queue()
            
            # Schedule the next update
            self.root.after(self.update_interval, self._schedule_update)
    
    def _process_message_queue(self):
        """Process any messages in the queue"""
        if not self.is_running:
            return

        try:
            while True:
                # Get message with timeout (non-blocking)
                message = self.message_queue.get(block=False)

                # Process based on message type
                try:
                    if message["type"] == "translation":
                        self._update_translation(message["russian"], message["english"])
                    elif message["type"] == "audio":
                        self._update_audio_level(message["level"])
                    elif message["type"] == "status":
                        self._update_status(message["text"])
                    elif message["type"] == "error":
                        self._show_error(message["text"])
                except Exception as e:
                    logger.error(f"Error processing message: {str(e)}")

                # Mark as processed
                self.message_queue.task_done()

        except queue.Empty:
            # No more messages to process
            pass
        except Exception as e:
            logger.error(f"Error processing UI message queue: {str(e)}")
    
    def _update_translation(self, russian_text: str, english_text: str):
        """Update the displayed translation"""
        if self.show_russian:
            self.russian_label.config(text=russian_text)
        self.english_label.config(text=english_text)
    
    def _update_audio_level(self, level: float):
        """Update the audio level meter"""
        # Update the progress bar (0-100)
        self.audio_meter["value"] = min(level, 100)
        # Update the label
        self.audio_level_label.config(text=f"Audio: {level:.1f}%")
    
    def _update_status(self, status_text: str):
        """Update the status message"""
        self.status_label.config(text=status_text)
    
    def _show_error(self, error_text: str):
        """Display an error message"""
        self._update_status(f"Error: {error_text}")
        # Could also show a popup for critical errors
    
    def _on_close(self):
        """Handle window close event"""
        self.is_running = False
        
        # Call external close callback if provided
        if self.on_close_callback is not None:
            self.on_close_callback()
        
        # Destroy the window
        self.root.destroy()
    
    def set_close_callback(self, callback: Callable[[], None]):
        """Set a callback to be called when the window is closed"""
        self.on_close_callback = callback
    
    # Public methods for adding messages to the queue
    
    def display_translation(self, russian_text: str, english_text: str):
        """Display a new translation (thread-safe)"""
        self.message_queue.put({
            "type": "translation",
            "russian": russian_text,
            "english": english_text
        })
    
    def update_audio_level(self, level: float):
        """Update the audio level indicator (thread-safe)"""
        self.message_queue.put({
            "type": "audio",
            "level": level
        })
    
    def update_status(self, status_text: str):
        """Update the status message (thread-safe)"""
        self.message_queue.put({
            "type": "status",
            "text": status_text
        })
    
    def show_error(self, error_text: str):
        """Display an error message (thread-safe)"""
        self.message_queue.put({
            "type": "error",
            "text": error_text
        })


# Simple test when run directly
if __name__ == "__main__":
    import random
    
    # Create and start the UI
    ui = CaptionDisplayUI(theme="default")
    
    # Define a function to simulate receiving translations
    def simulate_translations():
        russian_samples = [
            "Привет, как дела?",
            "Я изучаю программирование на Python.",
            "Это тест системы перевода в реальном времени.",
            "Машинное обучение - интересная область исследований.",
            "Искусственный интеллект меняет мир."
        ]
        
        english_samples = [
            "Hello, how are you?",
            "I am learning Python programming.",
            "This is a test of the real-time translation system.",
            "Machine learning is an interesting field of research.",
            "Artificial intelligence is changing the world."
        ]
        
        # Function to simulate audio levels
        def update_audio():
            if not ui.is_running:
                return
                
            # Generate random audio level between 0 and 100
            level = random.uniform(5.0, 95.0)
            ui.update_audio_level(level)
            
            # Schedule next update
            ui.root.after(300, update_audio)
        
        # Function to simulate translations
        def update_translation():
            if not ui.is_running:
                return
                
            # Pick a random sample
            idx = random.randint(0, len(russian_samples) - 1)
            ui.display_translation(russian_samples[idx], english_samples[idx])
            
            # Update status
            timestamp = time.strftime("%H:%M:%S")
            ui.update_status(f"Last updated: {timestamp}")
            
            # Schedule next translation (random interval between 2-5 seconds)
            interval = random.randint(2000, 5000)
            ui.root.after(interval, update_translation)
        
        # Start the simulation
        update_audio()
        update_translation()
    
    # Set a callback for when the window is closed
    ui.set_close_callback(lambda: print("UI window closed"))
    
    # Start the simulation in a separate thread
    simulation_thread = threading.Thread(target=simulate_translations)
    simulation_thread.daemon = True
    simulation_thread.start()
    
    # Start the UI (this will block until the window is closed)
    ui.start()