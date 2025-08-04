# Real-Time Speech-to-Speech Translation - Deployment Guide

## Quick Start Instructions

### Prerequisites

1. **Python Environment**
   ```bash
   # Ensure you're in the project directory
   cd c:/projects/real_time_trans
   
   # Install dependencies
   pip install -r requirements.txt
   ```

2. **Environment Configuration**
   ```bash
   # Set OpenAI API key (still needed for fallback/testing)
   set OPENAI_API_KEY=your_openai_api_key_here
   ```

### Running the Application

The application now consists of **two services** that need to be running:

#### Step 1: Start the M2M-100 Translation Service (Port 8001)

```bash
# In one terminal/command prompt
python -m uvicorn app.m2m_service:app --host 0.0.0.0 --port 8001 --reload
```

This will start the M2M-100 translation service at http://localhost:8001

**Expected Output:**
```
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     M2M-100 service initialized on device: cuda (or cpu)
INFO:     Model warmup completed
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8001
```

#### Step 2: Start the Main Application (Port 8000)

```bash
# In another terminal/command prompt
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

This will start the main application at http://localhost:8000

**Expected Output:**
```
INFO:     Started server process
INFO:     Starting Real-Time Translation system initialization...
INFO:     Whisper model 'small' preloaded successfully
INFO:     TTS engine initialized successfully
INFO:     All component tests passed - system ready for operation
INFO:     Uvicorn running on http://0.0.0.0:8000
```

#### Step 3: Access the Frontend

Open your web browser and navigate to:
```
http://localhost:8000
```

### Alternative: Single Command Startup

You can also run the main application directly with Python:

```bash
# Start M2M service (terminal 1)
python app/m2m_service.py

# Start main app (terminal 2) 
python main.py
```

## Service Architecture

```
┌─────────────────────────────────────────┐
│ Browser Frontend                        │
│ http://localhost:8000                   │
└─────────────┬───────────────────────────┘
              │ WebSocket + HTTP
┌─────────────▼───────────────────────────┐
│ Main Application (Port 8000)           │
│ • WebSocket handler                     │
│ • Pipeline coordinator                  │  
│ • ASR, TTS engines                      │
└─────────────┬───────────────────────────┘
              │ HTTP requests
┌─────────────▼───────────────────────────┐
│ M2M-100 Service (Port 8001)            │
│ • Meta M2M-100 418M model              │
│ • Session-based context                │
│ • GPU/CPU acceleration                  │
└─────────────────────────────────────────┘
```

## Configuration

The system uses `config.yaml` for configuration:

```yaml
# Translation service configuration  
translation:
  provider: "m2m"  # Uses M2M service by default
  
  m2m_service:
    url: "http://localhost:8001"
    timeout_seconds: 5.0
    max_retries: 3
```

## Health Checks

### M2M Service Health
```bash
curl http://localhost:8001/health
```

### Main Application Health  
```bash
curl http://localhost:8000/health/sessions
```

## Troubleshooting

### M2M Service Won't Start
- **Check GPU availability**: The service will fallback to CPU if CUDA is unavailable
- **Memory requirements**: Ensure at least 2GB RAM available
- **Port conflicts**: Make sure port 8001 is not in use

### Main Application Fails to Start
- **Missing OpenAI API key**: Still required for fallback functionality
- **M2M Service not running**: Ensure M2M service is started first
- **Missing dependencies**: Run `pip install -r requirements.txt`

### Translation Not Working
- **Check M2M service**: Verify http://localhost:8001/health returns healthy status
- **Check logs**: Monitor both service logs for error messages
- **Network connectivity**: Ensure main app can reach M2M service

## Performance Optimization

### GPU Acceleration (Recommended)
- Install CUDA toolkit for GPU acceleration
- The M2M service will automatically use GPU if available
- Expected performance: <200ms translation latency

### CPU-Only Mode
- Service automatically falls back to CPU if GPU unavailable  
- Expected performance: 500-1000ms translation latency
- Still functional for development and testing

## Production Deployment

### Docker Deployment (Recommended)
```bash
# Build M2M service image
docker build -t m2m-service -f Dockerfile.m2m .

# Build main app image  
docker build -t translation-app .

# Run with docker-compose
docker-compose up
```

### Manual Production Setup
```bash
# Install production WSGI server
pip install gunicorn

# Start M2M service (production)
gunicorn app.m2m_service:app -w 1 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8001

# Start main app (production)
gunicorn main:app -w 2 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000
```

## Development Mode

For development with auto-reload:

```bash
# Terminal 1: M2M service with reload
uvicorn app.m2m_service:app --reload --port 8001

# Terminal 2: Main app with reload  
uvicorn main:app --reload --port 8000
```

---

**Need Help?** Check the logs in the `logs/` directory for detailed error information.
