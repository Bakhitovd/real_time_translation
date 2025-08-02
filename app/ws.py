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
                        translated_audio, pipeline_info = await process_audio_pipeline(
                            audio_data, source_lang, target_lang
                        )
                        
                        if pipeline_info["success"] and translated_audio:
                            logging.info(f"Sending translated audio: {len(translated_audio)} bytes")
                            # Send translated audio back to client
                            await ws.send_bytes(translated_audio)
                        else:
                            # Send detailed error information to client
                            error_msg = pipeline_info.get("error", "Unknown pipeline error")
                            logging.warning(f"Pipeline failed: {error_msg}")
                            
                            await ws.send_text(json.dumps({
                                "type": "pipeline_error",
                                "message": error_msg,
                                "stages": pipeline_info.get("stages", {}),
                                "total_latency": pipeline_info.get("total_latency", 0)
                            }))
                            
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
        
async def process_audio_pipeline(audio_data: bytes, source_lang: str, target_lang: str) -> tuple[bytes, dict]:
    """Process audio through ASR -> MT -> TTS pipeline with detailed error reporting.

    Args:
        audio_data: Raw audio bytes (WebM/Opus format from frontend)
        source_lang: Source language code
        target_lang: Target language code

    Returns:
        Tuple of (translated_audio_bytes, pipeline_info_dict)
        If processing fails, returns (b"", error_info_dict)
    """
    pipeline_start = time.time()
    pipeline_info = {
        "success": False,
        "stages": {},
        "total_latency": 0,
        "error": None
    }
    
    try:
        # Step 0: Audio Format Conversion
        stage_start = time.time()
        logging.info("Starting audio format conversion...")
        
        wav_audio = convert_audio_to_wav(audio_data, input_format="webm")
        
        conversion_time = time.time() - stage_start
        pipeline_info["stages"]["conversion"] = {
            "success": True,
            "latency": conversion_time,
            "input_size": len(audio_data),
            "output_size": len(wav_audio)
        }
        logging.info(f"Audio conversion completed in {conversion_time*1000:.1f}ms")

        # Step 1: Speech-to-Text (ASR)
        stage_start = time.time()
        logging.info("Starting ASR (Speech-to-Text)...")
        
        transcript = transcribe_chunk(wav_audio, language=source_lang if source_lang != "auto" else None)
        
        asr_time = time.time() - stage_start
        pipeline_info["stages"]["asr"] = {
            "success": True,
            "latency": asr_time,
            "transcript": transcript,
            "transcript_length": len(transcript.strip())
        }

        if not transcript.strip():
            logging.info("No speech detected in audio chunk")
            pipeline_info["stages"]["asr"]["success"] = False
            pipeline_info["error"] = "No speech detected"
            return b"", pipeline_info

        logging.info(f"ASR completed in {asr_time*1000:.1f}ms: '{transcript[:50]}{'...' if len(transcript) > 50 else ''}'")

        # Step 2: Machine Translation (MT)
        stage_start = time.time()
        logging.info("Starting MT (Machine Translation)...")
        
        translated_text = await translate_text(transcript, source_lang, target_lang)
        
        mt_time = time.time() - stage_start
        pipeline_info["stages"]["mt"] = {
            "success": True,
            "latency": mt_time,
            "original_text": transcript,
            "translated_text": translated_text,
            "translation_length": len(translated_text.strip())
        }

        if not translated_text.strip():
            logging.warning("Translation resulted in empty text")
            pipeline_info["stages"]["mt"]["success"] = False
            pipeline_info["error"] = "Translation produced empty result"
            return b"", pipeline_info

        logging.info(f"MT completed in {mt_time*1000:.1f}ms: '{translated_text[:50]}{'...' if len(translated_text) > 50 else ''}'")

        # Step 3: Text-to-Speech (TTS)
        stage_start = time.time()
        logging.info("Starting TTS (Text-to-Speech)...")
        
        translated_audio = synthesize_text(translated_text)
        
        tts_time = time.time() - stage_start
        pipeline_info["stages"]["tts"] = {
            "success": True,
            "latency": tts_time,
            "input_text": translated_text,
            "output_size": len(translated_audio)
        }

        if not translated_audio:
            logging.error("TTS synthesis failed - no audio output")
            pipeline_info["stages"]["tts"]["success"] = False
            pipeline_info["error"] = "TTS synthesis failed"
            return b"", pipeline_info

        logging.info(f"TTS completed in {tts_time*1000:.1f}ms: {len(translated_audio)} bytes")

        # Pipeline Success
        total_time = time.time() - pipeline_start
        pipeline_info.update({
            "success": True,
            "total_latency": total_time
        })
        
        logging.info(f"Pipeline completed successfully in {total_time*1000:.1f}ms total")
        return translated_audio, pipeline_info

    except Exception as e:
        total_time = time.time() - pipeline_start
        error_msg = str(e)
        logging.error(f"Pipeline error after {total_time*1000:.1f}ms: {error_msg}")
        
        pipeline_info.update({
            "success": False,
            "total_latency": total_time,
            "error": error_msg,
            "error_type": type(e).__name__
        })
        
        return b"", pipeline_info
