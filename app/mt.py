"""
Machine Translation (MT) module.
Handles cloud API calls for text translation with robust network handling.
"""

import asyncio
import logging
import os
import time
from typing import Optional
import httpx
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion

class StreamingMT:
    """Machine Translation using OpenAI API with enhanced network resilience."""
    
    def __init__(self, model: str = "gpt-4.1-mini", api_key: Optional[str] = None):
        """Initialize OpenAI MT client with robust connection settings.
        
        Args:
            model: OpenAI model to use for translation
            api_key: OpenAI API key (if None, reads from environment)
        """
        self.model = model
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        
        if not self.api_key:
            raise ValueError("OpenAI API key not found. Set OPENAI_API_KEY environment variable.")
        
        # Configure robust HTTP client with connection pooling and timeouts
        http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=10.0,  # Connection timeout
                read=30.0,     # Read timeout
                write=10.0,    # Write timeout
                pool=60.0      # Pool timeout
            ),
            limits=httpx.Limits(
                max_keepalive_connections=10,
                max_connections=20,
                keepalive_expiry=30.0
            )
            # Note: httpx doesn't have a 'retries' parameter - we handle retries manually
        )
        
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            http_client=http_client
        )
        
        # Circuit breaker state
        self.failure_count = 0
        self.last_failure_time = 0
        self.circuit_open_duration = 60  # 60 seconds
        
        logging.info(f"Initialized OpenAI MT with model '{model}' and robust networking")
    
    def _is_circuit_open(self) -> bool:
        """Check if circuit breaker is open."""
        if self.failure_count >= 3:  # Open circuit after 3 failures
            time_since_failure = time.time() - self.last_failure_time
            if time_since_failure < self.circuit_open_duration:
                return True
            else:
                # Reset circuit breaker after timeout
                self.failure_count = 0
                logging.info("[MT] Circuit breaker reset - attempting to reconnect")
        return False

    async def _translate_with_retries(self, prompt: str, max_retries: int = 3) -> Optional[str]:
        """Execute translation with exponential backoff retries."""
        retry_delays = [0.5, 1.0, 2.0]  # Exponential backoff delays
        
        for attempt in range(max_retries):
            try:
                logging.debug(f"[MT] Translation attempt {attempt + 1}/{max_retries}")
                
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                    max_tokens=1000
                )
                
                # Success - reset failure counter
                self.failure_count = 0
                return response.choices[0].message.content.strip()
                
            except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.ConnectError) as e:
                logging.warning(f"[MT] Network error on attempt {attempt + 1}: {type(e).__name__}: {e}")
                
                if attempt < max_retries - 1:  # Don't delay on final attempt
                    delay = retry_delays[min(attempt, len(retry_delays) - 1)]
                    logging.info(f"[MT] Retrying in {delay}s...")
                    await asyncio.sleep(delay)
                else:
                    # Final attempt failed - update circuit breaker
                    self.failure_count += 1
                    self.last_failure_time = time.time()
                    logging.error(f"[MT] All {max_retries} attempts failed. Circuit breaker failure count: {self.failure_count}")
                    
            except Exception as e:
                # Non-network errors don't trigger circuit breaker
                logging.error(f"[MT] API error on attempt {attempt + 1}: {type(e).__name__}: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delays[min(attempt, len(retry_delays) - 1)])
                else:
                    logging.error(f"[MT] Translation failed after {max_retries} attempts")
        
        return None

    async def translate_text(self, text: str, source_lang: str, target_lang: str) -> str:
        """Translate text from source to target language with robust network handling.
        
        Args:
            text: Text to translate
            source_lang: Source language code (e.g., 'ru', 'en')
            target_lang: Target language code (e.g., 'en', 'ru')
            
        Returns:
            Translated text string
        """
        if not text.strip():
            return ""
        
        # Check circuit breaker
        if self._is_circuit_open():
            logging.warning("[MT] Circuit breaker is open - skipping translation")
            return text  # Return original text when circuit is open
        
        start_time = time.time()
        
        try:
            # Create translation prompt
            prompt = f"Translate the following {source_lang} text to {target_lang}:\n\n{text}"
            logging.debug(f"[MT] Starting translation: '{text[:50]}...'")
            
            # Execute with retries
            translated = await self._translate_with_retries(prompt)
            
            if translated is None:
                logging.error(f"[MT] Translation completely failed for: '{text[:50]}...'")
                return text  # Return original text if all retries failed
            
            duration = (time.time() - start_time) * 1000
            logging.info(
                f"[MT] ✅ Translated ({source_lang}->{target_lang}) in {duration:.1f}ms: "
                f"'{text[:50]}...' -> '{translated[:50]}...' "
                f"(input_len={len(text)}, output_len={len(translated)}, model={self.model})"
            )
            
            return translated

        except Exception as e:
            duration = (time.time() - start_time) * 1000
            logging.error(f"[MT] ❌ Translation failed after {duration:.1f}ms: {type(e).__name__}: {e}")
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
