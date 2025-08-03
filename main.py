"""
Entry point for the real-time translation backend.
Starts FastAPI app, includes API and WebSocket routes.
"""

# Load environment variables from .env file first
from dotenv import load_dotenv
load_dotenv()

import logging
import os
from fastapi import FastAPI
from app.api import router as api_router
from app.ws import router as ws_router
from app.config import load_config

# Configure logging: console + file, DEBUG level for manual debugging
import sys
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "manual_debug.log")

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file, mode="w", encoding="utf-8"),
    ]
)

app = FastAPI(title="Real-Time Speech Translation MVP")

# HTTP routes (serves frontend, health checks, etc.)
app.include_router(api_router)

# WebSocket routes (audio streaming)
app.include_router(ws_router)

async def _test_all_components():
    """Test all pipeline components with realistic data and measure performance.
    
    Returns:
        bool: True if all critical components pass, False otherwise
        
    Raises:
        Exception: If any critical component fails
    """
    import time
    import tempfile
    import wave
    import numpy as np
    
    total_start = time.time()
    test_results = []
    
    # Test 1: ASR Component
    logging.info("🔊 Testing ASR component...")
    asr_start = time.time()
    try:
        from app.asr import transcribe_chunk
        from app.temp_file_manager import managed_temp_file
        
        # Create test audio with some content (beep sound)
        duration = 1.0  # 1 second
        sample_rate = 16000
        frequency = 440  # A4 note
        t = np.linspace(0, duration, int(sample_rate * duration), False)
        audio_data = np.sin(2 * np.pi * frequency * t) * 0.3
        audio_int16 = (audio_data * 32767).astype(np.int16)
        
        # Create WAV file using managed temporary file
        with managed_temp_file(suffix=".wav", prefix="asr_test_") as temp_path:
            with wave.open(temp_path, 'wb') as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(sample_rate)
                wav_file.writeframes(audio_int16.tobytes())
            
            with open(temp_path, 'rb') as f:
                test_audio_bytes = f.read()
        
        # Test transcription
        transcript = transcribe_chunk(test_audio_bytes)
        asr_time = time.time() - asr_start
        logging.info(f"✅ ASR test completed in {asr_time:.2f}s (result: '{transcript}')")
        test_results.append(("ASR", True, None))
        
    except Exception as e:
        asr_time = time.time() - asr_start
        logging.error(f"❌ ASR test failed in {asr_time:.2f}s: {e}")
        test_results.append(("ASR", False, str(e)))
    
    # Test 2: MT Component
    logging.info("🌐 Testing MT component...")
    mt_start = time.time()
    try:
        from app.mt import translate_text
        
        test_text = "Hello, this is a test translation."
        translated = await translate_text(test_text, "en", "ru")
        mt_time = time.time() - mt_start
        logging.info(f"✅ MT test completed in {mt_time:.2f}s ('{test_text}' -> '{translated}')")
        test_results.append(("MT", True, None))
        
    except Exception as e:
        mt_time = time.time() - mt_start
        logging.error(f"❌ MT test failed in {mt_time:.2f}s: {e}")
        test_results.append(("MT", False, str(e)))
    
    # Test 3: TTS Component
    logging.info("🎵 Testing TTS component...")
    tts_start = time.time()
    try:
        from app.tts import synthesize_text
        
        test_text = "System test complete"
        audio_bytes = synthesize_text(test_text)
        tts_time = time.time() - tts_start
        
        if audio_bytes:
            logging.info(f"✅ TTS test completed in {tts_time:.2f}s (generated {len(audio_bytes)} bytes)")
            test_results.append(("TTS", True, None))
        else:
            logging.warning(f"⚠️ TTS test completed in {tts_time:.2f}s but no audio generated")
            test_results.append(("TTS", False, "No audio generated"))
            
    except Exception as e:
        tts_time = time.time() - tts_start
        logging.error(f"❌ TTS test failed in {tts_time:.2f}s: {e}")
        test_results.append(("TTS", False, str(e)))
    
    # Test 4: System Audio Processing
    logging.info("📡 Testing System Audio Capture component...")
    sac_start = time.time()
    try:
        from app.system_audio_capture import create_system_audio_handler
        
        handler = create_system_audio_handler()
        
        # Test with the same audio we used for ASR
        result = handler.process_system_audio(test_audio_bytes, 'wav')
        sac_time = time.time() - sac_start
        
        if result['success']:
            logging.info(f"✅ System Audio Capture test completed in {sac_time:.2f}s (speech={result['has_speech']}, energy={result['energy_level']:.4f})")
            test_results.append(("System Audio Capture", True, None))
        else:
            logging.warning(f"⚠️ System Audio Capture test completed in {sac_time:.2f}s but failed: {result['error']}")
            test_results.append(("System Audio Capture", False, result['error']))
            
    except Exception as e:
        sac_time = time.time() - sac_start
        logging.error(f"❌ System Audio Capture test failed in {sac_time:.2f}s: {e}")
        test_results.append(("System Audio Capture", False, str(e)))
    
    total_time = time.time() - total_start
    
    # Analyze results
    passed_tests = [name for name, passed, _ in test_results if passed]
    failed_tests = [(name, error) for name, passed, error in test_results if not passed]
    
    logging.info(f"🏁 Component testing completed in {total_time:.2f}s total")
    logging.info(f"📊 Results: {len(passed_tests)}/{len(test_results)} tests passed")
    
    if failed_tests:
        logging.error("❌ Failed components:")
        for name, error in failed_tests:
            logging.error(f"  - {name}: {error}")
        
        # Raise exception to prevent startup
        failed_names = [name for name, _ in failed_tests]
        raise RuntimeError(f"Critical component tests failed: {', '.join(failed_names)}. Cannot start server with broken components.")
    
    logging.info("✅ All component tests passed - system ready for operation")
    return True

@app.on_event("startup")
async def startup_event():
    """
    Initialize models and validate configuration on startup.
    This eliminates first-request delays and catches configuration issues early.
    """
    logging.info("Starting Real-Time Translation system initialization...")
    
    try:
        # Load configuration
        config = load_config()
        logging.info(f"Configuration loaded: {config}")
        
        # Validate OpenAI API key
        api_key_env = config.get("openai_api_key_env", "OPENAI_API_KEY")
        api_key = os.getenv(api_key_env)
        
        if not api_key:
            logging.error(f"OpenAI API key not found in environment variable '{api_key_env}'")
            logging.error("Set your OpenAI API key before starting the server")
            raise ValueError(f"Missing OpenAI API key in {api_key_env}")
        else:
            # Validate API key format (should start with 'sk-')
            if api_key.startswith('sk-'):
                logging.info("OpenAI API key found and appears valid")
            else:
                logging.warning("OpenAI API key found but format may be incorrect")
        
        # Preload Whisper model to eliminate first-request delay
        logging.info("Preloading Whisper model...")
        from app.asr import preload_model
        model_size = config.get("model", {}).get("asr", "base")
        preload_model(model_size)
        logging.info(f"Whisper model '{model_size}' preloaded successfully")
        
        # Initialize TTS engine
        logging.info("Initializing TTS engine...")
        from app.tts import initialize_tts
        initialize_tts()
        logging.info("TTS engine initialized successfully")
        
        # Test audio conversion capability
        logging.info("Testing audio conversion capability...")
        try:
            import ffmpeg
            logging.info("ffmpeg-python available for audio conversion")
        except ImportError:
            logging.error("ffmpeg-python not available - audio conversion will fail")
            raise ImportError("ffmpeg-python is required for audio conversion")
        
        # Comprehensive component testing
        logging.info("🧪 Starting comprehensive component testing...")
        await _test_all_components()
        
        logging.info("✅ System initialization completed successfully")
        logging.info("Ready to accept real-time translation requests")
        
    except RuntimeError as e:
        # Component test failure - this should prevent startup
        logging.error(f"❌ System initialization failed: {e}")
        logging.error("Server startup aborted due to failed component tests")
        logging.error("Fix the issues above before starting the server")
        # Re-raise to actually prevent startup
        raise e
        
    except Exception as e:
        logging.error(f"❌ System initialization failed: {e}")
        logging.error("Please fix the configuration issues before starting the server")
        # For other errors, still allow startup for debugging
        logging.warning("⚠️ Starting server despite initialization issues for debugging purposes")

@app.on_event("shutdown") 
async def shutdown_event():
    """Clean up resources on shutdown."""
    logging.info("Shutting down Real-Time Translation system...")
    
    # Clean up any resources if needed
    try:
        from app.tts import cleanup_tts
        cleanup_tts()
        logging.info("TTS resources cleaned up")
    except:
        pass
    
    logging.info("Shutdown complete")
