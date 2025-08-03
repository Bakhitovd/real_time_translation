"""
Module 7: M2M-100 Translation Service
Standalone GPU-optimized translation service with session-based context management.
Target: <200ms latency per 30-token chunk, 1k token context window per session.
"""

import asyncio
import logging
import time
from typing import Dict, Optional, Tuple, Any
from dataclasses import dataclass, field
from collections import defaultdict, deque
import torch
from transformers import M2M100ForConditionalGeneration, M2M100Tokenizer
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


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
        
        logging.info(f"Initializing M2M-100 service on {self.device}")
    
    async def initialize(self) -> None:
        """Load and warm up M2M-100 model."""
        try:
            # Load tokenizer and model
            self.tokenizer = M2M100Tokenizer.from_pretrained(self.model_name)
            self.model = M2M100ForConditionalGeneration.from_pretrained(self.model_name)
            
            if self.device == "cuda":
                self.model = self.model.cuda()
                logging.info(f"Model loaded on GPU: {torch.cuda.get_device_name()}")
            
            self.model.eval()
            
            # Warmup with dummy translation
            await self._warmup()
            logging.info("M2M-100 service initialized and warmed up")
            
        except Exception as e:
            logging.error(f"Failed to initialize M2M-100 service: {e}")
            raise
    
    async def _warmup(self) -> None:
        """Warm up model with dummy translation."""
        try:
            dummy_text = "Hello world"
            self.tokenizer.src_lang = "en"
            inputs = self.tokenizer(dummy_text, return_tensors="pt")
            if self.device == "cuda":
                inputs = {k: v.cuda() for k, v in inputs.items()}
            
            with torch.no_grad():
                _ = self.model.generate(
                    **inputs,
                    forced_bos_token_id=self.tokenizer.get_lang_id("ru"),
                    max_new_tokens=20,
                    num_beams=1
                )
            logging.info("Model warmup completed")
        except Exception as e:
            logging.warning(f"Warmup failed: {e}")
    
    async def translate(self, session_id: str, text: str, source_lang: str = "ru", 
                       target_lang: str = "en", use_context: bool = True) -> Tuple[str, Dict[str, Any]]:
        """
        Translate text with session-based context management.
        
        Args:
            session_id: Session identifier for context isolation
            text: Text to translate
            source_lang: Source language code
            target_lang: Target language code
            use_context: Whether to use session context
            
        Returns:
            (translated_text, metadata)
        """
        if not self.model or not self.tokenizer:
            raise HTTPException(status_code=503, detail="Service not initialized")
        
        start_time = time.time()
        
        try:
            # Get session context
            context = self.session_contexts[session_id]
            context_text = context.get_context() if use_context else ""
            
            # Prepare input with context
            if context_text and use_context:
                full_input = f"{context_text} {text}"
            else:
                full_input = text
            
            # Set source language and tokenize
            self.tokenizer.src_lang = source_lang
            inputs = self.tokenizer(full_input, return_tensors="pt", padding=True, truncation=True, max_length=512)
            
            if self.device == "cuda":
                inputs = {k: v.cuda() for k, v in inputs.items()}
            
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
            
            logging.info(
                f"Translation completed: session={session_id}, latency={latency_ms:.1f}ms, "
                f"context_tokens={context.token_count}, input_len={len(text)}"
            )
            
            return translation, metadata
            
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            logging.error(f"Translation failed for session {session_id}: {e}, latency={latency_ms:.1f}ms")
            raise HTTPException(status_code=500, detail=f"Translation failed: {str(e)}")
    
    def cleanup_session(self, session_id: str) -> bool:
        """Clean up session context."""
        if session_id in self.session_contexts:
            del self.session_contexts[session_id]
            logging.info(f"Cleaned up context for session {session_id}")
            return True
        return False
    
    def cleanup_stale_sessions(self, max_age_seconds: int = 3600) -> int:
        """Clean up sessions older than max_age_seconds."""
        current_time = time.time()
        stale_sessions = [
            sid for sid, ctx in self.session_contexts.items()
            if current_time - ctx.last_access > max_age_seconds
        ]
        
        for session_id in stale_sessions:
            self.cleanup_session(session_id)
        
        return len(stale_sessions)
    
    def get_service_stats(self) -> Dict[str, Any]:
        """Get service performance statistics."""
        avg_latency = self.total_latency / self.translation_count if self.translation_count > 0 else 0.0
        
        return {
            "translations_completed": self.translation_count,
            "average_latency_ms": avg_latency,
            "active_sessions": len(self.session_contexts),
            "gpu_available": torch.cuda.is_available(),
            "gpu_memory_allocated": torch.cuda.memory_allocated() if torch.cuda.is_available() else 0,
            "model_loaded": self.model is not None,
            "target_compliance": (avg_latency < 200.0) if self.translation_count > 0 else True
        }


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

# FastAPI app
app = FastAPI(title="M2M-100 Translation Service")


@app.on_event("startup")
async def startup_event():
    """Initialize service on startup."""
    await service.initialize()


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
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")
