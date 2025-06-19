"""
HTTP API routes for the real-time translation backend.
Serves frontend files and health checks.
"""

from fastapi import APIRouter
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import os

router = APIRouter()

# Get absolute path to frontend directory
frontend_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
print(f"Frontend path: {frontend_path}")
print(f"Frontend exists: {os.path.exists(frontend_path)}")

@router.get("/", response_class=FileResponse)
async def root():
    # Serve the actual frontend index.html
    index_path = os.path.join(frontend_path, "index.html")
    return FileResponse(index_path)

@router.get("/static/{file_path:path}")
async def serve_static(file_path: str):
    """Serve static files directly"""
    file_full_path = os.path.join(frontend_path, file_path)
    if os.path.exists(file_full_path):
        return FileResponse(file_full_path)
    return {"error": "File not found"}
