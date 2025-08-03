#!/usr/bin/env python3
"""
Real-time translation test script using sample audio files.
Simulates system audio capture → translation pipeline → output audio.

This script tests the complete Module 6 workflow:
1. Loads sample audio files (Russian/English)
2. Processes through SystemAudioCaptureHandler 
3. Sends to WebSocket translation pipeline
4. Saves translated audio output

Usage:
    python scripts/test_realtime_translation.py
"""

import asyncio
import json
import logging
import time
import websockets
from pathlib import Path
import sys
import os

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.system_audio_capture import (
    SystemAudioCaptureHandler,
    create_system_audio_handler
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class RealTimeTranslationTester:
    """Test real-time translation with sample audio files."""
    
    def __init__(self):
        self.websocket = None
        self.handler = create_system_audio_handler()
        self.output_dir = Path("output_audio")
        self.output_dir.mkdir(exist_ok=True)
        
        # Test configuration
        self.test_cases = [
            {
                "name": "Russian → English",
                "file": "input_audio/speach_sample_1_min_ru.m4a",
                "source_lang": "ru", 
                "target_lang": "en",
                "description": "Test Russian speech recognition and English translation"
            },
            {
                "name": "English → Russian", 
                "file": "input_audio/speach_sample_1_min_en.m4a",
                "source_lang": "en",
                "target_lang": "ru", 
                "description": "Test English speech recognition and Russian translation"
            }
        ]
    
    async def connect_websocket(self):
        """Connect to WebSocket translation service."""
        logger.info("Connecting to WebSocket at ws://localhost:8000/ws/translate")
        
        try:
            self.websocket = await websockets.connect("ws://localhost:8000/ws/translate")
            logger.info("✅ WebSocket connected successfully")
            return True
        except Exception as e:
            logger.error(f"❌ WebSocket connection failed: {e}")
            logger.error("Make sure the server is running: python main.py")
            return False
    
    async def configure_translation(self, source_lang: str, target_lang: str):
        """Configure translation language pair."""
        config = {
            "type": "config",
            "source_lang": source_lang,
            "target_lang": target_lang
        }
        
        await self.websocket.send(json.dumps(config))
        logger.info(f"📝 Configured translation: {source_lang} → {target_lang}")
        
        # Wait for acknowledgment
        response = await self.websocket.recv()
        ack = json.loads(response)
        
        if ack.get("type") == "config_ack":
            logger.info(f"✅ Configuration confirmed: {ack.get('source_lang')} → {ack.get('target_lang')}")
        else:
            logger.warning(f"⚠️ Unexpected response: {ack}")
    
    async def process_audio_file(self, file_path: str, test_name: str):
        """Process audio file through Module 6 and send to translation pipeline."""
        logger.info(f"\n🎵 Processing {test_name}: {file_path}")
        
        # Check if file exists
        if not Path(file_path).exists():
            logger.error(f"❌ Audio file not found: {file_path}")
            return None
        
        # Read audio file
        with open(file_path, "rb") as f:
            audio_data = f.read()
        
        logger.info(f"📁 Loaded audio file: {len(audio_data)} bytes")
        
        # Process through Module 6 System Audio Handler
        logger.info("🔄 Processing through Module 6 SystemAudioCaptureHandler...")
        
        start_time = time.time()
        result = self.handler.process_system_audio(audio_data, 'm4a')
        processing_time = time.time() - start_time
        
        # If no speech detected, try with lower threshold
        if not result.get("has_speech") and result.get("success"):
            logger.info(f"   No speech at default threshold, trying lower sensitivity...")
            # Extract wav_data and retry with lower threshold
            wav_data = result.get("wav_data")
            if wav_data:
                has_speech, energy = self.handler.detect_speech_activity(wav_data, threshold=0.005)
                result["has_speech"] = has_speech
                result["energy_level"] = energy
                logger.info(f"   Lower threshold result - Speech: {has_speech}, Energy: {energy:.3f}")
        
        if not result.get("success"):
            logger.error(f"❌ Module 6 processing failed: {result.get('error')}")
            return None
        
        logger.info(f"✅ Module 6 processing completed in {processing_time:.2f}s")
        logger.info(f"   Audio info: {result.get('audio_info', {})}")
        logger.info(f"   Duration: {result.get('audio_info', {}).get('duration_ms', 0)/1000:.1f}s")
        logger.info(f"   Speech detected: {result.get('has_speech')}")
        logger.info(f"   Energy level: {result.get('energy_level', 0):.3f}")
        
        if not result.get("has_speech"):
            logger.warning("⚠️ No speech detected in audio file")
            return None
        
        return result.get("wav_data")
    
    async def send_audio_chunks(self, wav_audio: bytes, chunk_size: int = 3000):
        """Send audio in chunks to simulate real-time streaming."""
        logger.info(f"📤 Sending audio in {chunk_size}ms chunks...")
        
        total_size = len(wav_audio)
        chunk_count = 0
        translated_audio_chunks = []
        
        # Send audio in chunks
        for i in range(0, total_size, chunk_size):
            chunk = wav_audio[i:i + chunk_size]
            chunk_count += 1
            
            logger.info(f"   Chunk {chunk_count}: {len(chunk)} bytes")
            
            # Send chunk
            await self.websocket.send(chunk)
            
            # Listen for responses (non-blocking)
            try:
                # Give a moment for processing
                await asyncio.sleep(0.1)
                
                # Check for responses
                while True:
                    try:
                        response = await asyncio.wait_for(self.websocket.recv(), timeout=0.1)
                        
                        if isinstance(response, bytes):
                            # Translated audio received
                            translated_audio_chunks.append(response)
                            logger.info(f"🎧 Received translated audio: {len(response)} bytes")
                        else:
                            # Text message (error or status)
                            message = json.loads(response)
                            if message.get("type") == "pipeline_error":
                                logger.error(f"❌ Pipeline error: {message.get('message')}")
                            else:
                                logger.info(f"📨 Message: {message}")
                    
                    except asyncio.TimeoutError:
                        break  # No more responses
                        
            except Exception as e:
                logger.warning(f"⚠️ Error receiving responses: {e}")
            
            # Small delay to simulate real-time streaming
            await asyncio.sleep(0.5)
        
        # Wait for final responses
        logger.info("⏳ Waiting for final translation results...")
        await asyncio.sleep(3)
        
        try:
            while True:
                response = await asyncio.wait_for(self.websocket.recv(), timeout=1.0)
                if isinstance(response, bytes):
                    translated_audio_chunks.append(response)
                    logger.info(f"🎧 Final translated audio: {len(response)} bytes")
        except asyncio.TimeoutError:
            pass
        
        return translated_audio_chunks
    
    def save_translated_audio(self, audio_chunks: list, test_name: str) -> str:
        """Save translated audio chunks to file."""
        if not audio_chunks:
            logger.warning("⚠️ No translated audio to save")
            return None
        
        # Combine all chunks
        combined_audio = b"".join(audio_chunks)
        
        # Generate output filename
        timestamp = int(time.time())
        filename = f"translated_{test_name.lower().replace(' ', '_').replace('→', 'to')}_{timestamp}.wav"
        output_path = self.output_dir / filename
        
        # Save to file
        with open(output_path, "wb") as f:
            f.write(combined_audio)
        
        logger.info(f"💾 Saved translated audio: {output_path}")
        logger.info(f"   Total size: {len(combined_audio)} bytes")
        
        return str(output_path)
    
    async def run_test_case(self, test_case: dict):
        """Run a single test case."""
        logger.info(f"\n{'='*60}")
        logger.info(f"🧪 TEST CASE: {test_case['name']}")
        logger.info(f"📝 {test_case['description']}")
        logger.info(f"{'='*60}")
        
        # Configure translation
        await self.configure_translation(
            test_case["source_lang"], 
            test_case["target_lang"]
        )
        
        # Process audio file
        wav_audio = await self.process_audio_file(
            test_case["file"], 
            test_case["name"]
        )
        
        if wav_audio is None:
            logger.error(f"❌ Test case failed: {test_case['name']}")
            return False
        
        # Send to translation pipeline
        translated_chunks = await self.send_audio_chunks(wav_audio)
        
        # Save results
        output_file = self.save_translated_audio(translated_chunks, test_case["name"])
        
        if output_file:
            logger.info(f"✅ Test case completed: {test_case['name']}")
            logger.info(f"🎧 Play translated audio: {output_file}")
            return True
        else:
            logger.error(f"❌ Test case failed: {test_case['name']}")
            return False
    
    async def run_all_tests(self):
        """Run all test cases."""
        logger.info("🚀 Starting Real-Time Translation Tests")
        logger.info(f"🎯 Testing {len(self.test_cases)} scenarios")
        
        # Connect to WebSocket
        if not await self.connect_websocket():
            return False
        
        results = []
        
        try:
            # Run each test case
            for test_case in self.test_cases:
                success = await self.run_test_case(test_case)
                results.append((test_case["name"], success))
        
        finally:
            # Close WebSocket
            if self.websocket:
                await self.websocket.close()
                logger.info("🔌 WebSocket disconnected")
        
        # Summary
        logger.info(f"\n{'='*60}")
        logger.info("📊 TEST RESULTS SUMMARY")
        logger.info(f"{'='*60}")
        
        passed = sum(1 for _, success in results if success)
        total = len(results)
        
        for test_name, success in results:
            status = "✅ PASSED" if success else "❌ FAILED"
            logger.info(f"  {test_name}: {status}")
        
        logger.info(f"\n🎯 Overall: {passed}/{total} tests passed")
        
        if passed == total:
            logger.info("🎉 All tests passed! Real-time translation system is working.")
        else:
            logger.warning("⚠️ Some tests failed. Check logs for details.")
        
        return passed == total


async def main():
    """Main test function."""
    print("\n" + "="*80)
    print("🎵 REAL-TIME SPEECH TRANSLATION SYSTEM TEST")
    print("🔧 Module 6: System Audio Capture Integration")
    print("="*80)
    
    tester = RealTimeTranslationTester()
    
    try:
        success = await tester.run_all_tests()
        exit_code = 0 if success else 1
        
    except KeyboardInterrupt:
        logger.info("\n⚠️ Test interrupted by user")
        exit_code = 1
    
    except Exception as e:
        logger.error(f"\n❌ Test failed with error: {e}")
        exit_code = 1
    
    print(f"\n{'='*80}")
    print("🏁 Test completed")
    print("="*80)
    
    sys.exit(exit_code)


if __name__ == "__main__":
    asyncio.run(main())
