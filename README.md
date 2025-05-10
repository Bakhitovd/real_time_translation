# Real-Time Audio Translation

This project is an AI-driven system that transcribes and translates live Russian audio into English text in real-time. It is designed to work with both USB microphones and pre-recorded audio files.

## Overview

The system is composed of several components:
1. **Audio Input:** Capture audio from a USB microphone with PyAudio
2. **Speech Recognition:** Use Hugging Face's Whisper model for high-quality Russian transcription
3. **Machine Translation:** Use OpenAI's API to translate Russian text to English with context preservation

## Features

- Direct USB microphone input with device selection
- Configurable audio chunk processing (3-5 second segments)
- Optional noise reduction and audio level monitoring
- High-quality Russian speech recognition with Whisper
- Context-aware translation that maintains conversation flow
- Multi-threaded design for parallel processing
- Colored, human-readable display mode for easy monitoring

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/real_time_translation.git
cd real_time_translation
```

### 2. Create a Virtual Environment

```bash
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Unix/Linux:
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure OpenAI API Key

Create a `.env` file in the project root:

```dotenv
OPENAI_API_KEY=your_openai_api_key_here
```

## Usage

### List Available Audio Devices

```bash
python translate_mic.py --list-devices
```

### Run with Default Settings

```bash
python translate_mic.py
```

### Run with Clean Display Mode

```bash
python translate_mic.py --quiet
```

### Run with Specific Device

```bash
python translate_mic.py --device DEVICE_INDEX
```

### Run with Custom Chunk Duration

```bash
python translate_mic.py --chunk-duration 5.0
```

## Module Descriptions

- **audio_input.py:**  
  Handles live audio capture from USB microphones with device selection, noise reduction, and level monitoring.

- **asr.py:**  
  Implements speech recognition using Hugging Face's Whisper model.

- **translation.py:**  
  Integrates with OpenAI API to translate Russian text to English with context awareness.

- **translate_mic.py:**  
  End-to-end script that combines all modules for continuous translation.

- **mic_test.py:**  
  Utility for testing microphone capture and transcription.

## Future Enhancements

- Add caption display UI for visual presentation of translations
- Create a unified main application with configuration system
- Implement auditing system for logging translations
- Add text-to-speech synthesis for audio output
- Develop a graphical user interface for improved accessibility

## Technical Requirements

- Python 3.8 or higher
- CUDA 11.8+ for optimal GPU acceleration
- PyTorch with CUDA support
- OpenAI API key

## License

This project is licensed under the MIT License.