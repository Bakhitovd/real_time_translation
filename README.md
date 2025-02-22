# Real-Time Audio Translation

This project is an AI-driven system that translates live Russian audio into English speech in real time. It is designed to work with both USB microphones and pre-recorded audio files.

## Overview

The system is composed of several components:
1. **Audio Input:** Capture audio from a USB mic or from recorded files.
2. **Real-Time ASR:** Use [Faster Whisper](https://github.com/guillaumekln/faster-whisper) on an RTX A4000 for low-latency transcription.
3. **Machine Translation:** Use OpenAI's GPT-4 API (or GPT-4 mini variant) to translate Russian text to English.
4. **Text-to-Speech (TTS):** Synthesize the English translation into audio.
5. **Playback:** Mix the original audio (at a lower volume) with the generated English TTS voice for simultaneous playback.

## Folder Structure
```bash
RealTimeAudioTranslation/
├── README.md
├── requirements.txt
├── .gitignore
└── src/
    ├── __init__.py
    ├── main.py
    ├── audio_input.py
    ├── asr.py
    ├── translation.py
    ├── tts.py
    └── mixer.py
```

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/real_time_translation.git
cd real_time_translation
```

### 2. Create a Virtual Environment (Recommended)

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create a `.env` file in the project root and add your OpenAI API key:

```dotenv
OPENAI_API_KEY=your_openai_api_key_here
```

### 5. Run the Project

Start the application:

```bash
python src/main.py
```

## Module Descriptions

- **audio_input.py:**  
  Handles live audio capture from a USB microphone and reading audio files.

- **asr.py:**  
  Implements real-time automatic speech recognition (ASR) using Faster Whisper.

- **translation.py:**  
  Integrates with the OpenAI API to translate transcribed Russian text into English.

- **tts.py:**  
  Converts the translated English text into speech using a TTS engine.

- **mixer.py:**  
  Mixes the original audio (at a lower volume) with the synthesized TTS audio for playback.

- **main.py:**  
  Orchestrates the entire pipeline by coordinating all the components.

## Future Enhancements

- Optimize chunking strategies for improved real-time performance.
- Enhance synchronization and mixing of the audio streams.
- Develop a graphical user interface (GUI) or web interface for improved user interaction.
- Explore alternative local translation models to reduce latency.

## License

This project is licensed under the MIT License.