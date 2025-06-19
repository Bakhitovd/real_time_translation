"""
WebSocket API routes for audio streaming and translation.
"""

import asyncio
import json
import logging
import time
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.asr import transcribe_chunk
from app.mt import translate_text
from app.tts import synthesize_text
from app.config import load_config
from app.utils import convert_audio_to_wav

router = APIRouter()

@router.websocket("/ws/translate")
async def websocket_translate(ws: WebSocket):
    """WebSocket endpoint for real-time audio translation.
    
    Expected client flow:
    1. Send configuration: {"type": "config", "source_lang": "ru", "target_lang": "en"}
    2. Send audio chunks: binary data (WAV format)
    3. Receive translated audio: binary data (WAV format)
    """
    await ws.accept()
    
    # Default configuration
    source_lang = "auto"
    target_lang = "en"
    
    try:
        logging.info("WebSocket translation session started")
        
        while True:
            # Receive message generically first
            message = await ws.receive()
            
            # Handle text messages (config)
            if message["type"] == "websocket.receive" and "text" in message:
                try:
                    config_data = json.loads(message["text"])
                    
                    if config_data.get("type") == "config":
                        source_lang = config_data.get("source_lang", "auto")
                        target_lang = config_data.get("target_lang", "en")
                        logging.info(f"Updated translation config: {source_lang} -> {target_lang}")
                        
                        # Send acknowledgment
                        await ws.send_text(json.dumps({
                            "type": "config_ack",
                            "source_lang": source_lang,
                            "target_lang": target_lang
                        }))
                except Exception as e:
                    logging.error(f"Error processing config: {e}")
            
            # Handle binary messages (audio)
            elif message["type"] == "websocket.receive" and "bytes" in message:
                try:
                    audio_data = message["bytes"]
                    
                    if len(audio_data) > 0:
                        # Debug: Log audio data info
                        logging.info(f"Received audio data: {len(audio_data)} bytes")
                        
                        # Save raw audio for debugging (first few chunks only)
                        if len(audio_data) > 1000:  # Only save substantial chunks
                            debug_path = f"debug_audio_{int(time.time())}.webm"
                            with open(debug_path, "wb") as f:
                                f.write(audio_data)
                            logging.info(f"Saved debug audio to: {debug_path}")
                        
                        # Process audio through translation pipeline
                        translated_audio = await process_audio_pipeline(
                            audio_data, source_lang, target_lang
                        )
                        
                        if translated_audio:
                            logging.info(f"Sending translated audio: {len(translated_audio)} bytes")
                            # Send translated audio back to client
                            await ws.send_bytes(translated_audio)
                        else:
                            logging.warning("No translated audio produced")
                            
                except Exception as e:
                    logging.error(f"Error processing audio: {e}")
                    await ws.send_text(json.dumps({
                        "type": "error",
                        "message": str(e)
                    }))
                    
    except WebSocketDisconnect:
        logging.info("WebSocket translation session ended")
    except Exception as e:
        logging.error(f"WebSocket error: {e}")
        
async def process_audio_pipeline(audio_data: bytes, source_lang: str, target_lang: str) -> bytes:
    """Process audio through ASR -> MT -> TTS pipeline.

    Args:
        audio_data: Raw audio bytes (WebM/Opus format from frontend)
        source_lang: Source language code
        target_lang: Target language code

    Returns:
        Translated audio bytes (WAV format)
    """
    try:
        # Step 0: Convert WebM/Opus to WAV/PCM
        wav_audio = convert_audio_to_wav(audio_data, input_format="webm")

        # Step 1: Speech-to-Text (ASR)
        logging.debug("Starting ASR...")
        transcript = transcribe_chunk(wav_audio, language=source_lang if source_lang != "auto" else None)

        if not transcript.strip():
            logging.debug("No speech detected in audio chunk")
            return b""

        logging.debug(f"ASR result: '{transcript[:50]}...'")

        # Step 2: Machine Translation (MT)
        logging.debug("Starting MT...")
        translated_text = await translate_text(transcript, source_lang, target_lang)

        if not translated_text.strip():
            logging.debug("Translation resulted in empty text")
            return b""

        logging.debug(f"MT result: '{translated_text[:50]}...'")

        # Step 3: Text-to-Speech (TTS)
        logging.debug("Starting TTS...")
        translated_audio = synthesize_text(translated_text)

        logging.debug(f"TTS completed: {len(translated_audio)} bytes")
        return translated_audio

    except Exception as e:
        logging.error(f"Pipeline error: {e}")
        return b""
