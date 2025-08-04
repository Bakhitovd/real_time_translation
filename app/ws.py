"""
WebSocket API routes for concurrent real-time audio translation.
Module 5: Concurrent Pipeline Integration with session-based coordination.
"""

import asyncio
import json
import logging
import time
import uuid
from typing import Optional, Dict, Any
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.asr import transcribe_chunk
from app.mt import translate_text
from app.tts import synthesize_text
from app.config import load_config
from app.utils import convert_audio_to_wav
from app.pipeline_coordinator import (
    StreamingPipelineCoordinator, 
    create_pipeline_coordinator,
    create_realtime_config,
    PipelineResult
)
from app.realtime_queue import ProcessingTask, ProcessingResult
from app.latency_monitor import create_latency_monitor
import io
import numpy as np
import soundfile as sf

router = APIRouter()

# Session registry for cleanup and monitoring
active_sessions: Dict[str, StreamingPipelineCoordinator] = {}

def generate_session_id() -> str:
    """Generate unique session identifier."""
    return f"session_{uuid.uuid4().hex[:8]}_{int(time.time())}"

def detect_speech_activity(audio_data: bytes, sensitivity: float = 0.8) -> tuple[bool, dict]:
    """
    Enhanced voice activity detection with confidence scoring.
    
    Args:
        audio_data: WAV audio bytes
        sensitivity: Detection sensitivity (0.0-1.0, higher = more sensitive)
    
    Returns:
        (has_speech: bool, metadata: dict) with confidence and energy metrics
    """
    try:
        # Convert bytes to audio array
        audio_io = io.BytesIO(audio_data)
        audio_array, sample_rate = sf.read(audio_io)
        
        if len(audio_array) == 0:
            return False, {"energy": 0.0, "confidence": 0.0}
        
        # Calculate RMS energy
        rms_energy = np.sqrt(np.mean(audio_array**2))
        
        # Adaptive threshold based on sensitivity
        base_threshold = 0.01
        threshold = base_threshold * (2.0 - sensitivity)  # Higher sensitivity = lower threshold
        
        has_speech = rms_energy > threshold
        confidence = min(rms_energy / threshold, 1.0) if threshold > 0 else 1.0
        
        return has_speech, {
            "energy": float(rms_energy),
            "confidence": float(confidence),
            "threshold": float(threshold)
        }
        
    except Exception as e:
        logging.warning(f"VAD detection failed: {e}, assuming speech present")
        return True, {"energy": 0.0, "confidence": 0.5, "error": str(e)}

# Global variables to store current session config
current_session_configs: Dict[str, Dict[str, str]] = {}

async def concurrent_audio_processor(task: ProcessingTask) -> PipelineResult:
    """
    Concurrent ASR->MT->TTS processor with integrated latency monitoring.
    
    Enables pipeline parallelization where multiple stages run simultaneously
    on different audio segments for sub-2s end-to-end latency.
    """
    latency_monitor = create_latency_monitor(target_ms=1800.0)
    latency_monitor.start_session()
    
    try:
        # Get session config for language settings
        session_config = current_session_configs.get(task.session_id, {})
        source_lang = session_config.get("source_lang", "auto")
        target_lang = session_config.get("target_lang", "en")
        
        # Stage 1: ASR with context
        logging.info(f"[Pipeline] 🎤 Starting ASR for session {task.session_id}")
        with latency_monitor.track_stage("asr", {"confidence_threshold": 0.8}):
            transcript = transcribe_chunk(
                task.audio_data, 
                language=source_lang if source_lang != "auto" else None
            )
        
        if not transcript.strip():
            session_data = latency_monitor.end_session()
            stage_latencies = {stage: metrics.duration_ms for stage, metrics in session_data.items()}
            total_latency = sum(stage_latencies.values())
            logging.warning(f"[Pipeline] ❌ ASR failed - no speech detected")
            return PipelineResult(
                session_id=task.session_id,
                chunk_ids=task.metadata.get("chunk_ids", []),
                success=False,
                error_message="No speech detected in audio segment",
                total_latency_ms=total_latency,
                stage_latencies=stage_latencies,
                metadata={"failed_stage": "asr", "transcript": "", "translation": ""}
            )
        
        logging.info(f"[Pipeline] ✅ ASR completed: '{transcript[:50]}...'")
        
        # Stage 2: Machine Translation with session context
        logging.info(f"[Pipeline] 🌐 Starting M2M MT for session {task.session_id}")
        with latency_monitor.track_stage("mt", {"source": source_lang, "target": target_lang}):
            translation = await translate_text(transcript, source_lang, target_lang, session_id=task.session_id)
        
        if not translation.strip():
            session_data = latency_monitor.end_session()
            stage_latencies = {stage: metrics.duration_ms for stage, metrics in session_data.items()}
            total_latency = sum(stage_latencies.values())
            logging.warning(f"[Pipeline] ❌ MT failed - empty translation")
            return PipelineResult(
                session_id=task.session_id,
                chunk_ids=task.metadata.get("chunk_ids", []),
                success=False,
                error_message="Translation produced empty result",
                total_latency_ms=total_latency,
                stage_latencies=stage_latencies,
                metadata={"failed_stage": "mt", "transcript": transcript, "translation": ""}
            )
        
        logging.info(f"[Pipeline] ✅ MT completed: '{translation[:50]}...'")
        
        # Stage 3: Text-to-Speech
        logging.info(f"[Pipeline] 🔊 Starting TTS for session {task.session_id}")
        with latency_monitor.track_stage("tts", {"text_length": len(translation)}):
            audio_result = synthesize_text(translation)
        
        if not audio_result:
            session_data = latency_monitor.end_session()
            stage_latencies = {stage: metrics.duration_ms for stage, metrics in session_data.items()}
            total_latency = sum(stage_latencies.values())
            logging.warning(f"[Pipeline] ❌ TTS failed - no audio generated")
            return PipelineResult(
                session_id=task.session_id,
                chunk_ids=task.metadata.get("chunk_ids", []),
                success=False,
                error_message="TTS synthesis failed",
                total_latency_ms=total_latency,
                stage_latencies=stage_latencies,
                metadata={"failed_stage": "tts", "transcript": transcript, "translation": translation}
            )
        
        logging.info(f"[Pipeline] ✅ TTS completed: {len(audio_result)} bytes")
        
        session_data = latency_monitor.end_session()
        stage_latencies = {stage: metrics.duration_ms for stage, metrics in session_data.items()}
        total_latency = sum(stage_latencies.values())
        
        return PipelineResult(
            session_id=task.session_id,
            chunk_ids=task.metadata.get("chunk_ids", []),
            translated_audio=audio_result,
            success=True,
            total_latency_ms=total_latency,
            stage_latencies=stage_latencies,
            metadata={
                "transcript": transcript,
                "translation": translation,
                "audio_size": len(audio_result)
            }
        )
        
    except Exception as e:
        session_data = latency_monitor.end_session()
        stage_latencies = {stage: metrics.duration_ms for stage, metrics in session_data.items()}
        total_latency = sum(stage_latencies.values())
        return PipelineResult(
            session_id=task.session_id,
            chunk_ids=task.metadata.get("chunk_ids", []),
            success=False,
            error_message=f"Pipeline error: {str(e)}",
            total_latency_ms=total_latency,
            stage_latencies=stage_latencies
        )

@router.websocket("/ws/translate")
async def websocket_translate(ws: WebSocket):
    """
    WebSocket endpoint for concurrent real-time audio translation.
    
    Features:
    - Session-based coordination with pipeline parallelization
    - Non-blocking audio input and result streaming
    - Sub-2s latency with comprehensive monitoring
    - Automatic error recovery and backpressure control
    """
    session_id = generate_session_id()
    coordinator: Optional[StreamingPipelineCoordinator] = None
    
    # Default configuration
    source_lang = "auto"
    target_lang = "en"
    
    await ws.accept()
    
    try:
        logging.info(f"Starting concurrent translation session: {session_id}")
        
        # Initialize session coordinator with real-time config
        config = create_realtime_config()
        coordinator = create_pipeline_coordinator(session_id, config)
        active_sessions[session_id] = coordinator
        
        # Start concurrent pipeline processing
        await coordinator.start_pipeline(concurrent_audio_processor)
        
        logging.info(f"Session {session_id} coordinator started successfully")
        
        while True:
            message = await ws.receive()
            
            # Handle text messages (configuration)
            if message["type"] == "websocket.receive" and "text" in message:
                try:
                    config_data = json.loads(message["text"])
                    
                    if config_data.get("type") == "config":
                        source_lang = config_data.get("source_lang", "auto")
                        target_lang = config_data.get("target_lang", "en")
                        
                        # Store session config for processor function
                        current_session_configs[session_id] = {
                            "source_lang": source_lang,
                            "target_lang": target_lang
                        }
                        
                        logging.info(f"Session {session_id}: Updated config {source_lang} -> {target_lang}")
                        
                        await ws.send_text(json.dumps({
                            "type": "config_ack",
                            "session_id": session_id,
                            "source_lang": source_lang,
                            "target_lang": target_lang
                        }))
                        
                except Exception as e:
                    logging.error(f"Session {session_id}: Config error: {e}")
            
            # Handle binary messages (audio) with concurrent processing
            elif message["type"] == "websocket.receive" and "bytes" in message:
                try:
                    audio_data = message["bytes"]
                    
                    if len(audio_data) > 0:
                        # Convert to WAV format
                        wav_audio = convert_audio_to_wav(audio_data, input_format="webm")
                        
                        # Enhanced voice activity detection
                        has_speech, vad_metadata = detect_speech_activity(wav_audio)
                        
                        # Add audio chunk to coordinator's buffer
                        chunk_added = await coordinator.add_audio_chunk(
                            wav_audio, 
                            duration_ms=len(wav_audio) // 32,  # Approximate duration
                            has_speech=has_speech
                        )
                        
                        if not chunk_added:
                            logging.warning(f"Session {session_id}: Buffer overflow, applying backpressure")
                            await coordinator.handle_backpressure()
                        
                        # Check for completed processing results (non-blocking)
                        while result := await coordinator.get_next_result():
                            if result.success and result.translated_audio:
                                # Send debug information about successful pipeline
                                debug_metadata = result.metadata or {}
                                
                                # Send transcript preview
                                if debug_metadata.get("transcript"):
                                    await ws.send_text(json.dumps({
                                        "type": "debug_transcript",
                                        "text": debug_metadata["transcript"],
                                        "stage_latencies": result.stage_latencies
                                    }))
                                
                                # Send translation preview
                                if debug_metadata.get("translation"):
                                    await ws.send_text(json.dumps({
                                        "type": "debug_translation", 
                                        "text": debug_metadata["translation"],
                                        "total_latency_ms": result.total_latency_ms
                                    }))
                                
                                # Send success status
                                await ws.send_text(json.dumps({
                                    "type": "debug_pipeline_complete",
                                    "success": True,
                                    "audio_size": len(result.translated_audio),
                                    "stage_latencies": result.stage_latencies,
                                    "total_latency_ms": result.total_latency_ms
                                }))
                                
                                logging.info(f"Session {session_id}: Sending translated audio: {len(result.translated_audio)} bytes")
                                await ws.send_bytes(result.translated_audio)
                            else:
                                # Send detailed error information with debug context
                                debug_metadata = result.metadata or {}
                                failed_stage = debug_metadata.get("failed_stage", "unknown")
                                
                                # Send stage-specific debug info even on failure
                                if debug_metadata.get("transcript"):
                                    await ws.send_text(json.dumps({
                                        "type": "debug_transcript",
                                        "text": debug_metadata["transcript"],
                                        "stage_latencies": result.stage_latencies
                                    }))
                                
                                if debug_metadata.get("translation"):
                                    await ws.send_text(json.dumps({
                                        "type": "debug_translation",
                                        "text": debug_metadata["translation"],
                                        "stage_latencies": result.stage_latencies
                                    }))
                                
                                # Send detailed error information
                                await ws.send_text(json.dumps({
                                    "type": "debug_pipeline_error",
                                    "session_id": session_id,
                                    "message": result.error_message,
                                    "failed_stage": failed_stage,
                                    "latency_ms": result.total_latency_ms,
                                    "stage_latencies": result.stage_latencies,
                                    "transcript": debug_metadata.get("transcript", ""),
                                    "translation": debug_metadata.get("translation", "")
                                }))
                        
                        # Send session health status periodically
                        if coordinator.is_healthy():
                            stats = coordinator.get_pipeline_stats()
                            if stats.sessions_processed % 10 == 0:  # Every 10 processed segments
                                await ws.send_text(json.dumps({
                                    "type": "health_status",
                                    "session_id": session_id,
                                    "avg_latency_ms": stats.avg_pipeline_latency_ms,
                                    "compliance_rate": stats.target_compliance_rate,
                                    "processed_segments": stats.sessions_processed
                                }))
                        
                except Exception as e:
                    logging.error(f"Session {session_id}: Audio processing error: {e}")
                    await ws.send_text(json.dumps({
                        "type": "error",
                        "session_id": session_id,
                        "message": str(e)
                    }))
                    
    except WebSocketDisconnect:
        logging.info(f"Session {session_id}: WebSocket disconnected")
    except Exception as e:
        logging.error(f"Session {session_id}: WebSocket error: {e}")
    finally:
        # Graceful session cleanup
        if coordinator:
            try:
                await coordinator.stop_pipeline()
                logging.info(f"Session {session_id}: Pipeline stopped successfully")
            except Exception as e:
                logging.error(f"Session {session_id}: Cleanup error: {e}")
        
        # Remove from active sessions and session configs
        active_sessions.pop(session_id, None)
        current_session_configs.pop(session_id, None)
        logging.info(f"Session {session_id}: Cleanup completed")

@router.get("/health/sessions")
async def get_active_sessions():
    """Get health information about active translation sessions."""
    session_info = {}
    
    for session_id, coordinator in active_sessions.items():
        try:
            stats = coordinator.get_pipeline_stats()
            session_info[session_id] = {
                "healthy": coordinator.is_healthy(),
                "avg_latency_ms": stats.avg_pipeline_latency_ms,
                "compliance_rate": stats.target_compliance_rate,
                "processed_segments": stats.sessions_processed,
                "buffer_stats": stats.buffer_stats,
                "queue_stats": stats.queue_stats
            }
        except Exception as e:
            session_info[session_id] = {"error": str(e)}
    
    return {
        "active_sessions": len(active_sessions),
        "sessions": session_info
    }
