# Real-Time Audio Translation

This project is an AI-driven system that transcribes and translates live Russian audio into English text in real-time. It is designed to work with both USB microphones and pre-recorded audio files.

## Overview

The system is composed of several components:
1. **Audio Input:** Capture audio from a USB microphone with PyAudio
2. **Speech Recognition:** Use Hugging Face's Whisper model for high-quality Russian transcription
3. **Machine Translation:** Use OpenAI's API to translate Russian text to English with context preservation
4. **Caption Display UI:** Visual presentation of translations with a customizable Tkinter interface

## Features

- Direct USB microphone input with device selection
- Configurable audio chunk processing (3-5 second segments)
- Optional noise reduction and audio level monitoring
- High-quality Russian speech recognition with Whisper
- Context-aware translation that maintains conversation flow
- Multi-threaded design for parallel processing
- Colored, human-readable display mode for easy monitoring
- Caption Display UI with customizable themes (default, dark, light)
- Real-time audio level visualization and status indicators

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
# or
python src/main.py --list-devices
```

### Run with Caption Display UI (Recommended)

```bash
python src/main.py
```

### Run with Command-Line Interface Only

```bash
python translate_mic.py
# or
python src/main.py --console-only
```

### UI Customization Options

```bash
# Choose UI theme (default, dark, or light)
python src/main.py --theme dark

# Hide Russian text in UI
python src/main.py --hide-russian
```

### Run with Specific Device

```bash
python src/main.py --device DEVICE_INDEX
```

### Run with Custom Chunk Duration

```bash
python src/main.py --chunk-duration 5.0
```

## Module Descriptions

- **audio_input.py:**
  Handles live audio capture from USB microphones with device selection, noise reduction, and level monitoring.

- **asr.py:**
  Implements speech recognition using Hugging Face's Whisper model.

- **translation.py:**
  Integrates with OpenAI API to translate Russian text to English with context awareness.

- **caption_ui.py:**
  Provides a Tkinter-based UI for displaying captions with customizable themes and styling.

- **main.py:**
  Integrates all components into a complete application with Caption Display UI.

- **translate_mic.py:**
  Command-line script for continuous translation without graphical interface.

- **mic_test.py:**
  Utility for testing microphone capture and transcription.

- **tts.py:**
  Text-to-speech functionality for synthesizing spoken translations.

## Future Enhancements

- **Performance Optimization:** Improve transcription speed and translation efficiency
- **Bidirectional Translation:** Add English to Russian translation support
- **Text-to-Speech Integration:** Enable spoken output of translations using the existing TTS module
- **Advanced UI Features:** Add transcript history, search functionality, and more customization options
- **Auditing System:** Implement logging of translations with timestamps and audio segments

## Technical Requirements

- Python 3.8 or higher
- CUDA 11.8+ for optimal GPU acceleration
- PyTorch with CUDA support
- OpenAI API key
- Tkinter for the Caption Display UI (included with most Python installations)

## License

This project is licensed under the MIT License.