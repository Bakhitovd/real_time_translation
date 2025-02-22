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

