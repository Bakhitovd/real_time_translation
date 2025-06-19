"""
Configuration loader for ASR, MT, TTS, and general settings.
Loads config.yaml and exposes settings as a simple configuration system.
"""

import yaml
import os
from typing import Optional, Dict, Any

class Settings:
    """Simple settings class without Pydantic dependency."""
    
    def __init__(self, **kwargs):
        self.asr_model: str = kwargs.get("asr_model", "base")
        self.mt_provider: str = kwargs.get("mt_provider", "openai")
        self.tts_engine: str = kwargs.get("tts_engine", "pyttsx3")
        self.mt_api_key: Optional[str] = kwargs.get("mt_api_key")
        self.chunk_size_ms: int = kwargs.get("chunk_size_ms", 200)

def load_config(path: str = "config.yaml") -> Dict[str, Any]:
    """Load configuration from YAML file.
    
    Args:
        path: Path to config.yaml file
        
    Returns:
        Configuration dictionary
    """
    try:
        with open(path, "r") as f:
            config = yaml.safe_load(f)
        return config
    except FileNotFoundError:
        # Return default config if file not found
        return {
            "model": {
                "asr": "small",
                "mt_engine": "gpt-4.1-mini",
                "voice_models": {
                    "en": "default",
                    "ru": "default"
                }
            },
            "openai_api_key_env": "OPENAI_API_KEY",
            "logging": {
                "level": "INFO"
            },
            "coqui": {
                "use_cuda": False
            }
        }

def load_settings() -> Settings:
    """Load settings using simple Settings class."""
    config = load_config()
    
    # Extract relevant settings from config
    asr_model = config.get("model", {}).get("asr", "small")
    mt_engine = config.get("model", {}).get("mt_engine", "gpt-4.1-mini")
    api_key_env = config.get("openai_api_key_env", "OPENAI_API_KEY")
    
    return Settings(
        asr_model=asr_model,
        mt_provider="openai",
        tts_engine="pyttsx3",
        mt_api_key=os.getenv(api_key_env),
        chunk_size_ms=200
    )

def get_asr_model_size() -> str:
    """Get ASR model size from config."""
    config = load_config()
    return config.get("model", {}).get("asr", "small")

def get_mt_engine() -> str:
    """Get MT engine from config."""
    config = load_config()
    return config.get("model", {}).get("mt_engine", "gpt-4.1-mini")

def get_voice_model(language: str) -> str:
    """Get TTS voice model for specific language."""
    config = load_config()
    voice_models = config.get("model", {}).get("voice_models", {})
    return voice_models.get(language, "default")
