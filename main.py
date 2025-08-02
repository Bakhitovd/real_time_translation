"""
Entry point for the real-time translation backend.
Starts FastAPI app, includes API and WebSocket routes.
"""

import logging
import os
from fastapi import FastAPI
from app.api import router as api_router
from app.ws import router as ws_router
from app.config import load_config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

app = FastAPI(title="Real-Time Speech Translation MVP")

# HTTP routes (serves frontend, health checks, etc.)
app.include_router(api_router)

# WebSocket routes (audio streaming)
app.include_router(ws_router)

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
        
        logging.info("✅ System initialization completed successfully")
        logging.info("Ready to accept real-time translation requests")
        
    except Exception as e:
        logging.error(f"❌ System initialization failed: {e}")
        logging.error("Please fix the configuration issues before starting the server")
        # Don't exit here - let the app start but with warnings
        # This allows for debugging and manual configuration fixes

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
