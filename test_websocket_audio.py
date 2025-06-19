#!/usr/bin/env python3
"""
Test WebSocket audio processing by sending WebM data directly
"""

import asyncio
import websockets
import json

async def test_websocket_audio():
    """Test sending WebM audio to WebSocket endpoint"""
    
    try:
        # Connect to WebSocket
        uri = "ws://localhost:8000/ws/translate"
        async with websockets.connect(uri) as websocket:
            print("Connected to WebSocket")
            
            # Send configuration
            config = {
                "type": "config",
                "source_lang": "ru",
                "target_lang": "en"
            }
            await websocket.send(json.dumps(config))
            print("Sent config")
            
            # Wait for config acknowledgment
            response = await websocket.recv()
            print(f"Received: {response}")
            
            # Load WebM test file
            with open("test_sample.webm", "rb") as f:
                webm_data = f.read()
            
            print(f"Sending WebM audio: {len(webm_data)} bytes")
            
            # Send WebM audio data
            await websocket.send(webm_data)
            print("Sent WebM audio data")
            
            # Wait for translated audio response
            try:
                audio_response = await asyncio.wait_for(websocket.recv(), timeout=30.0)
                print(f"Received translated audio: {len(audio_response)} bytes")
                
                # Save the response
                with open("websocket_translated_audio.wav", "wb") as f:
                    f.write(audio_response)
                print("Saved translated audio to websocket_translated_audio.wav")
                
            except asyncio.TimeoutError:
                print("Timeout waiting for audio response")
                
    except Exception as e:
        print(f"WebSocket test error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_websocket_audio())
