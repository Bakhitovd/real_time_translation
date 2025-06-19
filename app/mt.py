"""
Machine Translation (MT) module.
Handles cloud API calls for text translation.
"""

import asyncio
import logging
import os
from typing import Optional
import openai
from openai import AsyncOpenAI

class StreamingMT:
    """Machine Translation using OpenAI API for real-time translation."""
    
    def __init__(self, model: str = "gpt-4.1-mini", api_key: Optional[str] = None):
        """Initialize OpenAI MT client.
        
        Args:
            model: OpenAI model to use for translation
            api_key: OpenAI API key (if None, reads from environment)
        """
        self.model = model
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        
        if not self.api_key:
            raise ValueError("OpenAI API key not found. Set OPENAI_API_KEY environment variable.")
        
        self.client = AsyncOpenAI(api_key=self.api_key)
        logging.info(f"Initialized OpenAI MT with model '{model}'")
    
    async def translate_text(self, text: str, source_lang: str, target_lang: str) -> str:
        """Translate text from source to target language.
        
        Args:
            text: Text to translate
            source_lang: Source language code (e.g., 'ru', 'en')
            target_lang: Target language code (e.g., 'en', 'ru')
            
        Returns:
            Translated text string
        """
        if not text.strip():
            return ""
        
        try:
            # Create translation prompt
            prompt = f"Translate the following {source_lang} text to {target_lang}:\n\n{text}"
            
            # Call OpenAI API
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=1000
            )
            
            translated = response.choices[0].message.content.strip()
            logging.debug(f"MT translated: '{text[:30]}...' -> '{translated[:30]}...'")
            return translated
            
        except Exception as e:
            logging.error(f"MT translation failed: {e}")
            return text  # Return original text if translation fails

# Global MT instance for reuse
_mt_instance = None

def get_mt_instance(model: str = "gpt-4.1-mini") -> StreamingMT:
    """Get global MT instance, creating if needed."""
    global _mt_instance
    if _mt_instance is None:
        _mt_instance = StreamingMT(model)
    return _mt_instance

async def translate_text(text: str, source_lang: str = "auto", target_lang: str = "en") -> str:
    """Convenience function to translate text using global MT instance.
    
    Args:
        text: Text to translate
        source_lang: Source language code (auto-detect if 'auto')
        target_lang: Target language code
        
    Returns:
        Translated text string
    """
    mt = get_mt_instance()
    return await mt.translate_text(text, source_lang, target_lang)
