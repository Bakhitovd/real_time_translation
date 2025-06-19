"""
Entry point for the real-time translation backend.
Starts FastAPI app, includes API and WebSocket routes.
"""

from fastapi import FastAPI
from app.api import router as api_router
from app.ws import router as ws_router

app = FastAPI(title="Real-Time Speech Translation MVP")

# HTTP routes (serves frontend, health checks, etc.)
app.include_router(api_router)

# WebSocket routes (audio streaming)
app.include_router(ws_router)
