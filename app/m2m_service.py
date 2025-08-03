import asyncio
import logging
import time
from typing import Dict, Optional, Tuple, Any
from dataclasses import dataclass, field
from collections import defaultdict, deque

import torch
from transformers import M2M100ForConditionalGeneration, M2M100Tokenizer
from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager
from pydantic import BaseModel

# Configure root logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class SessionContext:
    """Context buffer for translation session."""
    buffer: deque = field(default_factory=lambda: deque(maxlen=3))  # Last 3 sentences
    token_count: int = 0
    last_access: float = field(default_factory=time.time)
    
    def add_text(self, text: str, tokenizer) -> None:
        """Add text to context buffer with token counting."""
        stripped_text = text.strip()
        if stripped_text:
            tokens = len(tokenizer.encode(stripped_text))
            self.buffer.append(stripped_text)
            self.token_count = sum(len(tokenizer.encode(t)) for t in self.buffer)
            self.last_access = time.time()
            
            # Truncate if exceeding 1k tokens
            while self.token_count > 1000 and len(self.buffer) > 1:
                removed = self.buffer.popleft()
                self.token_count -= len(tokenizer.encode(removed))
    
    def get_context(self) -> str:
        """Get formatted context string."""
        return " ".join(self.buffer) if self.buffer else ""


class M2MTranslationService:
    """GPU-optimized M2M-100 translation service with session context management."""
    
    def __init__(self, model_name: str = "facebook/m2m100_418M"):
        """Initialize M2M-100 service with GPU optimization."""
        self.model_name = model_name
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = None
        self.tokenizer = None
        self.session_contexts: Dict[str, SessionContext] = defaultdict(SessionContext)
        self.translation_count = 0
        self.total_latency = 0.0
        
        logger.info(f"Initializing M2M-100 service on device: {self.device}")
        if self.device == "cuda":
            logger.info(f"CUDA available: {torch.cuda.get_device_name(0)}")
        else:
            logger.warning("CUDA not available. Using CPU. This will be significantly slower.")
    
    async def initialize(self) -> None:
        """Load and warm up M2M-100 model."""
        try:
            # Load tokenizer and model
            logger.info(f"Loading tokenizer and model: {self.model_name}")
            self.tokenizer = M2M100Tokenizer.from_pretrained(self.model_name)
            self.model = M2M100ForConditionalGeneration.from_pretrained(self.model_name)
            
            if self.device == "cuda":
                self.model = self.model.cuda()
                logger.info("Model moved to GPU memory")
                logger.info(f"GPU memory allocated at init: {torch.cuda.memory_allocated() / 1024**2:.2f} MB")
            
            self.model.eval()
            
            # Warmup with dummy translation
            await self._warmup()
            logger.info("M2M-100 service initialized and warmed up")
            
        except Exception as e:
            logger.error(f"Failed to initialize M2M-100 service: {e}")
            raise
    
    async def _warmup(self) -> None:
        """Warm up model with dummy translation."""
        try:
            dummy_text = "Hello world"
            self.tokenizer.src_lang = "en"
            inputs = self.tokenizer(dummy_text, return_tensors="pt")
            if self.device == "cuda":
                inputs = {k: v.cuda() for k, v in inputs.items()}
                logger.debug("Warmup inputs moved to GPU")
            
            with torch.no_grad():
                _ = self.model.generate(
                    **inputs,
                    forced_bos_token_id=self.tokenizer.get_lang_id("ru"),
                    max_new_tokens=20,
                    num_beams=1
                )
            logger.info("Model warmup completed")
        except Exception as e:
            logger.warning(f"Warmup failed: {e}")
    
    async def translate(self, session_id: str, text: str, source_lang: str = "ru", 
                       target_lang: str = "en", use_context: bool = True) -> Tuple[str, Dict[str, Any]]:
        """
        Translate text with session-based context management.
        """
        if not self.model or not self.tokenizer:
            raise HTTPException(status_code=503, detail="Service not initialized")
        
        start_time = time.time()
        
        try:
            # Log beginning of translation
            logger.info(f"Starting translation for session={session_id} text_len={len(text)}")
            # Get session context
            context = self.session_contexts[session_id]
            context_text = context.get_context() if use_context else ""
            
            # Prepare input with context
            full_input = f"{context_text} {text}" if context_text and use_context else text
            
            # Set source language and tokenize
            self.tokenizer.src_lang = source_lang
            inputs = self.tokenizer(full_input, return_tensors="pt", padding=True, truncation=True, max_length=512)
            
            if self.device == "cuda":
                inputs = {k: v.cuda() for k, v in inputs.items()}
                logger.debug("Translation inputs moved to GPU")
                logger.debug(f"GPU memory before generate: {torch.cuda.memory_allocated() / 1024**2:.2f} MB")
            
            # Generate translation
            with torch.no_grad():
                outputs = self.model.generate(
                    **inputs,
                    forced_bos_token_id=self.tokenizer.get_lang_id(target_lang),
                    max_new_tokens=80,
                    num_beams=2,
                    early_stopping=True,
                    do_sample=False
                )
            
            # Decode result
            translation = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
            
            # Update session context with source text
            context.add_text(text, self.tokenizer)
            
            # Calculate metrics
            latency_ms = (time.time() - start_time) * 1000
            self.translation_count += 1
            self.total_latency += latency_ms
            
            metadata = {
                "latency_ms": latency_ms,
                "context_tokens": context.token_count,
                "used_context": bool(context_text and use_context),
                "input_length": len(text),
                "output_length": len(translation),
                "source_lang": source_lang,
                "target_lang": target_lang
            }
            
            # Log completion and GPU stats
            logger.info(
                f"Translation completed: session={session_id}, latency={latency_ms:.1f}ms, "
                f"context_tokens={context.token_count}, input_len={len(text)}"
            )
            if self.device == "cuda":
                logger.info(f"GPU memory after generate: {torch.cuda.memory_allocated() / 1024**2:.2f} MB")
            
            return translation, metadata
            
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            logger.error(f"Translation failed for session {session_id}: {e}, latency={latency_ms:.1f}ms")
            raise HTTPException(status_code=500, detail=f"Translation failed: {str(e)}")
    
    def cleanup_session(self, session_id: str) -> bool:
        """Clean up session context."""
        if session_id in self.session_contexts:
            del self.session_contexts[session_id]
            logger.info(f"Cleaned up context for session {session_id}")
            return True
        return False
    
    def cleanup_stale_sessions(self, max_age_seconds: int = 3600) -> int:
        """Clean up sessions older than max_age_seconds."""
        current_time = time.time()
        stale_sessions = [
            sid for sid, ctx in self.session_contexts.items()
            if current_time - ctx.last_access > max_age_seconds
        ]
        
        for sid in stale_sessions:
            self.cleanup_session(sid)
        
        logger.info(f"Cleaned up {len(stale_sessions)} stale sessions")
        return len(stale_sessions)
    
    def get_service_stats(self) -> Dict[str, Any]:
        """Get service performance statistics."""
        avg_latency = self.total_latency / self.translation_count if self.translation_count > 0 else 0.0
        stats = {
            "translations_completed": self.translation_count,
            "average_latency_ms": avg_latency,
            "active_sessions": len(self.session_contexts),
            "gpu_available": torch.cuda.is_available(),
            "gpu_memory_allocated": torch.cuda.memory_allocated() if torch.cuda.is_available() else 0,
            "model_loaded": self.model is not None,
            "target_compliance": (avg_latency < 200.0) if self.translation_count > 0 else True
        }
        logger.debug(f"Service stats: {stats}")
        return stats

# Pydantic models for API
class TranslationRequest(BaseModel):
    session_id: str
    text: str
    source_lang: str = "ru"
    target_lang: str = "en"
    use_context: bool = True


class TranslationResponse(BaseModel):
    translation: str
    metadata: Dict[str, Any]


# Global service instance
service = M2MTranslationService()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await service.initialize()
    yield
    # Shutdown - cleanup if needed

# FastAPI app with lifespan events
app = FastAPI(title="M2M-100 Translation Service", lifespan=lifespan)


@app.post("/translate", response_model=TranslationResponse)
async def translate_text(request: TranslationRequest):
    """Translate text with session-based context."""
    translation, metadata = await service.translate(
        request.session_id,
        request.text,
        request.source_lang,
        request.target_lang,
        request.use_context
    )
    return TranslationResponse(translation=translation, metadata=metadata)


@app.delete("/sessions/{session_id}")
async def cleanup_session(session_id: str):
    """Clean up specific session context."""
    cleaned = service.cleanup_session(session_id)
    return {"session_id": session_id, "cleaned": cleaned}


@app.get("/health")
async def health_check():
    """Service health and performance statistics."""
    return service.get_service_stats()


@app.post("/cleanup")
async def cleanup_stale_sessions(max_age_seconds: int = 3600):
    """Clean up sessions older than specified age."""
    cleaned_count = service.cleanup_stale_sessions(max_age_seconds)
    return {"cleaned_sessions": cleaned_count}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("m2m_service:app", host="0.0.0.0", port=8001, log_level="info")
