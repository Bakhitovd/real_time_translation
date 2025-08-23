"""
Machine Translation (MT) module.
Handles M2M-100 translation service calls with robust network handling.
"""

import asyncio
import logging
import time
from typing import Optional, Dict, Any
import httpx
from app.config import load_config

class StreamingMT:
    """Machine Translation using M2M-100 service with enhanced network resilience."""
    
    def __init__(self, service_url: Optional[str] = None, timeout_seconds: Optional[float] = None):
        """Initialize M2M-100 MT client with robust connection settings.
        
        Args:
            service_url: M2M service URL (if None, reads from config)
            timeout_seconds: Request timeout in seconds (if None, reads from config)
        """
        config = load_config()
        translation_config = config.get("translation", {})
        m2m_config = translation_config.get("m2m_service", {})
        
        self.service_url = service_url or m2m_config.get("url", "http://localhost:8001")
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else m2m_config.get("timeout_seconds", 5.0)
        self.max_retries = m2m_config.get("max_retries", 3)
        
        # Configure robust HTTP client with connection pooling and timeouts
        self.http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=10.0,  # Connection timeout
                read=self.timeout_seconds,     # Read timeout
                write=10.0,    # Write timeout
                pool=60.0      # Pool timeout
            ),
            limits=httpx.Limits(
                max_keepalive_connections=10,
                max_connections=20,
                keepalive_expiry=30.0
            )
        )
        
        # Circuit breaker state (configurable)
        self.failure_count = 0
        self.last_failure_time = 0
        # configurable thresholds from config (with sensible defaults)
        self.circuit_failure_threshold = m2m_config.get("failure_threshold", 3)
        self.circuit_open_duration = m2m_config.get("circuit_open_duration", 60)  # seconds
        self.backoff_base = m2m_config.get("backoff_base", 0.5)
        self.max_backoff = m2m_config.get("max_backoff", 10.0)

        logging.info(
            f"Initialized M2M-100 MT service at '{self.service_url}' with {self.timeout_seconds}s timeout, "
            f"circuit_failure_threshold={self.circuit_failure_threshold}, circuit_open_duration={self.circuit_open_duration}s"
        )
    
    def _is_circuit_open(self) -> bool:
        """Check if circuit breaker is open using configurable thresholds."""
        try:
            if self.failure_count >= self.circuit_failure_threshold:
                time_since_failure = time.time() - self.last_failure_time
                if time_since_failure < self.circuit_open_duration:
                    return True
                else:
                    # Reset circuit breaker after timeout
                    logging.info("[MT] Circuit breaker timeout expired; resetting counters and attempting reconnection")
                    self.failure_count = 0
                    self.last_failure_time = 0
        except Exception:
            # In case configuration is invalid, keep circuit closed to avoid permanent disabling
            return False
        return False

    async def _translate_with_retries(self, session_id: str, text: str, source_lang: str, target_lang: str, max_retries: int = None) -> Optional[str]:
        """Execute M2M translation with exponential backoff + jitter retries and improved error classification."""
        import random

        if max_retries is None:
            max_retries = self.max_retries

        for attempt in range(max_retries):
            try:
                logging.debug(f"[MT] M2M translation attempt {attempt + 1}/{max_retries}")

                # Prepare request payload for M2M service
                payload = {
                    "session_id": session_id,
                    "text": text,
                    "source_lang": source_lang,
                    "target_lang": target_lang,
                    "use_context": True  # Enable context-aware translation
                }

                response = await self.http_client.post(
                    f"{self.service_url}/translate",
                    json=payload,
                    timeout=self.timeout_seconds
                )

                # Raise for HTTP errors (will be caught below)
                response.raise_for_status()

                # Parse JSON safely
                try:
                    result = response.json()
                except Exception:
                    result = {}
                translation = result.get("translation", "")

                # Success - reset failure counter and return
                self.failure_count = 0
                self.last_failure_time = 0
                return translation

            except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.ConnectError, httpx.RemoteProtocolError) as e:
                logging.warning(f"[MT] Network error on attempt {attempt + 1}: {type(e).__name__}: {e}")

                # On transient network errors, use exponential backoff with jitter
                if attempt < max_retries - 1:
                    backoff = min(self.backoff_base * (2 ** attempt), self.max_backoff)
                    jitter = random.uniform(0, backoff * 0.1)
                    delay = backoff + jitter
                    logging.info(f"[MT] Retrying in {delay:.2f}s (attempt {attempt + 2}/{max_retries})")
                    await asyncio.sleep(delay)
                    continue
                else:
                    # Final failure -> increment failure counter for circuit breaker
                    self.failure_count += 1
                    self.last_failure_time = time.time()
                    logging.error(f"[MT] All {max_retries} network attempts failed. failure_count={self.failure_count}")

            except httpx.HTTPStatusError as e:
                status = getattr(e.response, "status_code", None)
                body = getattr(e.response, "text", "")
                logging.error(f"[MT] HTTP error on attempt {attempt + 1}: {status} - {body}")

                # For 5xx server errors treat as transient; for 4xx treat as permanent
                if status and 500 <= int(status) < 600 and attempt < max_retries - 1:
                    backoff = min(self.backoff_base * (2 ** attempt), self.max_backoff)
                    jitter = random.uniform(0, backoff * 0.1)
                    delay = backoff + jitter
                    logging.info(f"[MT] Server error, retrying in {delay:.2f}s")
                    await asyncio.sleep(delay)
                    continue
                else:
                    # Permanent failure, update circuit breaker
                    self.failure_count += 1
                    self.last_failure_time = time.time()
                    logging.error(f"[MT] Permanent HTTP failure, incrementing failure_count to {self.failure_count}")

            except Exception as e:
                logging.error(f"[MT] Unexpected error on attempt {attempt + 1}: {type(e).__name__}: {e}")
                if attempt < max_retries - 1:
                    backoff = min(self.backoff_base * (2 ** attempt), self.max_backoff)
                    jitter = random.uniform(0, backoff * 0.1)
                    delay = backoff + jitter
                    logging.info(f"[MT] Retrying after unexpected error in {delay:.2f}s")
                    await asyncio.sleep(delay)
                    continue
                else:
                    logging.error(f"[MT] Final unexpected failure after {max_retries} attempts")
                    # Do not increment failure_count for unexpected parsing errors (avoid false opens)

        return None

    async def translate_text(self, text: str, source_lang: str, target_lang: str, session_id: str = "default") -> str:
        """Translate text using M2M-100 service with robust network handling.
        
        Args:
            text: Text to translate
            source_lang: Source language code (e.g., 'ru', 'en')
            target_lang: Target language code (e.g., 'en', 'ru')
            session_id: Session ID for context-aware translation
            
        Returns:
            Translated text string
        """
        if not text.strip():
            return ""
        
        # Check circuit breaker
        if self._is_circuit_open():
            logging.warning("[MT] Circuit breaker is open - skipping M2M translation")
            return text  # Return original text when circuit is open
        
        start_time = time.time()
        
        try:
            logging.debug(f"[MT] Starting M2M translation: '{text[:50]}...'")
            
            # Execute with retries
            translated = await self._translate_with_retries(session_id, text, source_lang, target_lang)
            
            if translated is None:
                logging.error(f"[MT] M2M translation completely failed for: '{text[:50]}...'")
                return text  # Return original text if all retries failed
            
            duration = (time.time() - start_time) * 1000
            logging.info(
                f"[MT] ✅ M2M Translated ({source_lang}->{target_lang}) in {duration:.1f}ms: "
                f"'{text[:50]}...' -> '{translated[:50]}...' "
                f"(input_len={len(text)}, output_len={len(translated)}, session={session_id})"
            )
            
            return translated

        except Exception as e:
            duration = (time.time() - start_time) * 1000
            logging.error(f"[MT] ❌ M2M translation failed after {duration:.1f}ms: {type(e).__name__}: {e}")
            return text  # Return original text if translation fails
    
    async def check_service_health(self) -> Dict[str, Any]:
        """Check M2M service health and return status."""
        try:
            response = await self.http_client.get(f"{self.service_url}/health", timeout=5.0)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logging.error(f"[MT] M2M service health check failed: {e}")
            return {"error": str(e), "healthy": False}
    
    async def cleanup(self):
        """Cleanup HTTP client resources."""
        if self.http_client:
            await self.http_client.aclose()

# Global MT instance for reuse
_mt_instance = None

def get_mt_instance() -> StreamingMT:
    """Get global M2M MT instance, creating if needed."""
    global _mt_instance
    if _mt_instance is None:
        _mt_instance = StreamingMT()
    return _mt_instance

async def translate_text(text: str, source_lang: str = "auto", target_lang: str = "en", session_id: str = "default") -> str:
    """Convenience function to translate text using global M2M MT instance.
    
    Args:
        text: Text to translate
        source_lang: Source language code (auto-detect if 'auto')
        target_lang: Target language code
        session_id: Session ID for context-aware translation
        
    Returns:
        Translated text string
    """
    mt = get_mt_instance()
    return await mt.translate_text(text, source_lang, target_lang, session_id)
