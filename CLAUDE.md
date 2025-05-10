# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Real-Time Audio Translation is a system that captures Russian speech from a USB microphone, transcribes it to text, translates it to English with context awareness, and displays the translations as captions. The system is designed to be simplified from the original implementation, focusing on:

1. Direct USB microphone input
2. Context-aware translations
3. Caption display
4. (Future) Auditing capabilities

## System Components

### Implemented Architecture

1. **Audio Input**: Capture audio directly from USB microphone using PyAudio
   - Implemented in `src/audio_input.py`
   - Supports device selection, noise reduction, and audio level monitoring
   - Processes audio in configurable chunks (default 3-second segments)

2. **Speech Recognition (ASR)**: Using Hugging Face's Whisper model for Russian speech transcription
   - Implemented in `src/asr.py`
   - Uses the "whisper-large-v3-turbo" model with CUDA acceleration when available
   - Supports both file-based and microphone input transcription

3. **Translation**: Translate Russian text to English using OpenAI's API with context preservation
   - Implemented in `src/translation.py`
   - Uses gpt-4o-mini model with structured JSON output format
   - Maintains conversation history for context-aware translations

4. **Caption Display**: (Not yet implemented) Show translated text in a simple UI
5. **Context Management**: Implemented within the translation module for context preservation
6. **Auditing**: (Future) Log translations and audio segments for review

## Setup Requirements

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set up OpenAI API key in .env file
echo "OPENAI_API_KEY=your_api_key_here" > .env
```

Note: The project requires CUDA for optimal performance. It uses PyTorch with CUDA 11.8 and the Hugging Face Transformers library for speech recognition.

## Implementation Plan

### 1. Audio Capture Module
- Use PyAudio to directly capture audio from USB microphone
- Process audio in configurable chunks (3-5 second segments)
- Apply noise reduction as needed

### 2. Transcription Module
- Use Faster-Whisper for efficient ASR
- Support language detection or fixed Russian input
- Implement confidence scoring

### 3. Translation Module
- Use OpenAI API for translation
- Maintain conversation context between segments
- Implement fallback mechanisms for API failures

### 4. Caption Display
- Create a simple GUI using Tkinter or PyQt
- Display captions with timing information
- Support styles/themes for readability

### 5. Context Management
- Implement sliding window for conversation history
- Optimize context size for token efficiency
- Provide mechanisms to reset context when needed

### 6. Auditing System (Future)
- Log translations with timestamps
- Store audio segments selectively
- Provide interface for reviewing translations

## Running the Application

The project includes several scripts for testing and running different components:

```bash
# Run audio capture and transcription test
python mic_test.py [--device DEVICE_INDEX] [--duration SECONDS] [--list-devices]

# Run continuous transcription and translation
python translate_mic.py [--device DEVICE_INDEX] [--list-devices] [--chunk-duration SECONDS]

# Run in quiet mode with colored, human-readable output
python translate_mic.py --quiet

# Run in debug mode with verbose logging
python translate_mic.py --debug

# Test ASR with a specific audio file
python asr_simple_test.py
```

The main application (not yet implemented) will be run with:
```bash
python src/main.py
```

## Development Notes

- Focus on modularity to allow easy component replacement
- Prioritize low-latency processing for real-time experience
- Design with extensibility in mind for future improvements
- Keep configuration parameters in a central location
- Implement appropriate error handling for each component
- Avoid overengineering - write simple, minimal code that fulfills requirements
- Do not rewrite working code unless absolutely necessary
- Test code after implementation before moving to the next component
- Ensure each module works correctly with reasonable test cases, but avoid excessive testing

## Technical Implementation Notes

### Audio Processing
- PyAudio is used for microphone capture
- Audio is processed in configurable chunks (default 3 seconds)
- Audio level monitoring helps filter out silence
- Noise reduction is applied optionally

### Speech Recognition
- Uses Hugging Face Transformers implementation of Whisper
- Faster-Whisper had CUDA compatibility issues
- The `whisper-large-v3-turbo` model provides good quality Russian transcription
- Temporary WAV files are used for processing chunks

### Translation
- OpenAI API with `gpt-4o-mini` model provides efficient translation
- JSON response format ensures consistent output structure
- Conversation context is maintained between chunks for coherent translation
- API key is loaded from .env file using python-dotenv

### Multi-threading
- Audio capture, transcription, and translation run in separate threads
- Queues are used to pass data between threads
- Thread coordination uses standard Python threading primitives

### User Interface
- Command-line interface with different display modes
- Quiet mode (`--quiet`) for clean, human-readable output
- Colored output using the colorama library:
  - Audio levels displayed in cyan
  - Russian transcriptions in yellow
  - English translations in green
  - Error messages in red
- Debug mode (`--debug`) for verbose technical logging