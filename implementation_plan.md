# Implementation Plan for Simplified Real-Time Translation

## 1. Audio Input Module (src/audio_input.py)

This module will be simplified to directly capture audio from the USB microphone:

- Replace socket server with PyAudio for direct microphone access
- Maintain similar chunk/buffer handling for consistency
- Add device selection capability for multiple microphones
- Implement basic audio level monitoring
- Add optional noise filtering

```python
# Key function signature
def mic_stream(chunk_duration=3, device_index=None):
    """Yields audio segments as numpy arrays from USB microphone"""
    # Implementation details...
    yield audio_np  # normalized float32 array
```

## 2. ASR Module (src/asr.py)

Keep using Faster-Whisper but simplify configuration:

- Provide options for model size selection (tiny, small, medium)
- Add language auto-detection option
- Implement confidence scoring for transcriptions
- Optimize for lower latency

```python
# Key function signature
def transcribe(audio_np, language="ru", confidence_threshold=0.6):
    """Transcribe audio to text with optional confidence filtering"""
    # Implementation details...
    return transcription, confidence
```

## 3. Translation Module (src/translation.py)

Enhance context awareness:

- Implement sliding context window with configurable size
- Add summarization for long contexts to reduce token usage
- Implement fallback options if API fails
- Add translation confidence scoring

```python
# Key function signature
def translate_text(text, context_size=5):
    """Translate text with context awareness"""
    # Implementation details...
    return translated_text
```

## 4. Caption Display (src/caption_display.py)

New module for displaying captions:

- Create a simple UI with configurable appearance
- Support varying display durations based on text length
- Implement fade-in/fade-out effects
- Show original text alongside translation (optional)
- Add support for saving caption history

```python
# Key function signature
class CaptionDisplay:
    def show_caption(self, text, duration=None):
        """Display a caption with optional duration override"""
        # Implementation details...
```

## 5. Context Manager (src/context_manager.py)

New module to handle conversation context:

- Store and manage conversation history
- Provide methods to add/remove/update context entries
- Implement context pruning for token efficiency
- Support manual context reset

```python
# Key function signature
class ConversationContext:
    def add_entry(self, source_text, translated_text):
        """Add a new entry to the conversation context"""
        # Implementation details...
    
    def get_context(self, max_tokens=1000):
        """Get formatted context for translation"""
        # Implementation details...
```

## 6. Main Controller (src/main.py)

Simplify the main controller:

- Initialize and coordinate all components
- Implement cleaner shutdown procedures
- Add configuration loading from file
- Provide CLI arguments for common settings

```python
# Main execution flow
def main():
    """Main execution flow for the translation system"""
    # Setup components
    # Process audio stream
    # Display captions
    # Handle shutdown
```

## 7. Future Auditing System (src/auditing.py)

Placeholder for future auditing implementation:

- Define interfaces for capturing translation data
- Create storage structure for logs
- Plan for audio segment archiving
- Design review interface

## Implementation Phases

1. **Phase 1**: Core functionality (audio capture, ASR, translation)
2. **Phase 2**: Caption display and UI
3. **Phase 3**: Context management refinement
4. **Phase 4**: Auditing system

## Dependencies Update

Add to requirements.txt:
```
pyaudio
tkinter
```