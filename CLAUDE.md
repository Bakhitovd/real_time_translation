# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Real-Time Audio Translation is a system that captures Russian speech from a USB microphone, transcribes it to text, translates it to English with context awareness, and displays the translations as captions. The system is designed to be simplified from the original implementation, focusing on:

1. Direct USB microphone input
2. Context-aware translations
3. Caption display
4. (Future) Auditing capabilities

## System Components

### Planned Architecture

1. **Audio Input**: Capture audio directly from USB microphone using PyAudio
2. **Speech Recognition (ASR)**: Use Whisper or Faster-Whisper for Russian speech transcription
3. **Translation**: Translate Russian text to English using OpenAI's API with context preservation
4. **Caption Display**: Show translated text in a simple UI with appropriate timing
5. **Context Management**: Maintain conversation history for context-aware translations
6. **Auditing**: (Future) Log translations and audio segments for review

## Setup Requirements

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set up OpenAI API key
export OPENAI_API_KEY=your_openai_api_key_here
```

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

```bash
# Run the main application
python src/main.py
```

## Development Notes

- Focus on modularity to allow easy component replacement
- Prioritize low-latency processing for real-time experience
- Design with extensibility in mind for future improvements
- Keep configuration parameters in a central location
- Implement appropriate error handling for each component