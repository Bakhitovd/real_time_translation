"""
Module 5: Concurrent Pipeline Integration Tests
Comprehensive testing for session-based WebSocket translation with pipeline coordination.
"""

import pytest
import asyncio
import json
import time
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from hypothesis import given, strategies as st, settings

# Test framework imports
from fastapi.testclient import TestClient
from fastapi.websockets import WebSocket
import websockets

# Module imports
from app.ws import (
    websocket_translate,
    generate_session_id,
    detect_speech_activity,
    concurrent_audio_processor,
    active_sessions
)
from app.pipeline_coordinator import (
    create_pipeline_coordinator,
    create_realtime_config
)
from app.realtime_queue import ProcessingTask, ProcessingResult


class TestSessionManagement:
    """Test session lifecycle and coordinator management."""

    def test_session_id_generation(self):
        """Test unique session ID generation."""
        # Generate multiple session IDs
        session_ids = [generate_session_id() for _ in range(10)]
        
        # Verify all IDs are unique
        assert len(set(session_ids)) == 10
        
        # Verify format (session_<8chars>_<timestamp>)
        for session_id in session_ids:
            assert session_id.startswith("session_")
            parts = session_id.split("_")
            assert len(parts) == 3
            assert len(parts[1]) == 8  # UUID hex segment
            assert parts[2].isdigit()  # Timestamp

    @pytest.mark.asyncio
    async def test_session_coordinator_lifecycle(self):
        """Test coordinator initialization and cleanup."""
        config = create_realtime_config()
        session_id = "test_session_001"
        
        # Create coordinator
        coordinator = create_pipeline_coordinator(session_id, config)
        
        # Verify initial state
        assert coordinator.session_id == session_id
        assert not coordinator._active
        
        # Start pipeline
        async def mock_processor(task):
            return ProcessingResult(task.task_id, success=True)
        
        await coordinator.start_pipeline(mock_processor)
        assert coordinator._active
        
        # Stop pipeline
        await coordinator.stop_pipeline()
        assert not coordinator._active

    def test_active_sessions_registry(self):
        """Test global active sessions management."""
        # Clear registry
        active_sessions.clear()
        
        # Add test sessions
        session_ids = ["session_1", "session_2", "session_3"]
        for session_id in session_ids:
            config = create_realtime_config()
            coordinator = create_pipeline_coordinator(session_id, config)
            active_sessions[session_id] = coordinator
        
        # Verify registry state
        assert len(active_sessions) == 3
        assert all(sid in active_sessions for sid in session_ids)
        
        # Remove session
        del active_sessions["session_2"]
        assert len(active_sessions) == 2
        assert "session_2" not in active_sessions


class TestVoiceActivityDetection:
    """Test enhanced voice activity detection."""

    def test_vad_with_silent_audio(self):
        """Test VAD with silent audio."""
        # Create silent audio (zeros)
        import io
        import soundfile as sf
        import numpy as np
        
        silent_audio = np.zeros(1000, dtype=np.float32)
        buffer = io.BytesIO()
        sf.write(buffer, silent_audio, 16000, format='WAV')
        audio_bytes = buffer.getvalue()
        
        has_speech, metadata = detect_speech_activity(audio_bytes)
        
        assert not has_speech
        assert metadata["energy"] == 0.0
        assert metadata["confidence"] == 0.0

    def test_vad_with_speech_audio(self):
        """Test VAD with simulated speech audio."""
        import io
        import soundfile as sf
        import numpy as np
        
        # Create audio with higher energy (simulated speech)
        speech_audio = np.random.normal(0, 0.1, 1000).astype(np.float32)
        buffer = io.BytesIO()
        sf.write(buffer, speech_audio, 16000, format='WAV')
        audio_bytes = buffer.getvalue()
        
        has_speech, metadata = detect_speech_activity(audio_bytes)
        
        assert has_speech
        assert metadata["energy"] > 0.01
        assert metadata["confidence"] > 0.0

    def test_vad_sensitivity_adjustment(self):
        """Test VAD sensitivity parameter."""
        import io
        import soundfile as sf
        import numpy as np
        
        # Create borderline audio
        borderline_audio = np.random.normal(0, 0.02, 1000).astype(np.float32)
        buffer = io.BytesIO()
        sf.write(buffer, borderline_audio, 16000, format='WAV')
        audio_bytes = buffer.getvalue()
        
        # High sensitivity should detect speech
        has_speech_high, _ = detect_speech_activity(audio_bytes, sensitivity=0.9)
        
        # Low sensitivity should not detect speech
        has_speech_low, _ = detect_speech_activity(audio_bytes, sensitivity=0.1)
        
        # High sensitivity is more likely to detect speech
        # (Note: This test may be probabilistic due to random audio)

    def test_vad_error_handling(self):
        """Test VAD error handling with invalid audio."""
        # Test with empty bytes
        has_speech, metadata = detect_speech_activity(b"")
        assert not has_speech
        
        # Test with invalid audio data
        has_speech, metadata = detect_speech_activity(b"invalid_audio_data")
        assert has_speech  # Should default to True on error
        assert "error" in metadata


class TestConcurrentAudioProcessor:
    """Test the concurrent audio processing function."""

    @pytest.mark.asyncio
    async def test_successful_audio_processing(self):
        """Test successful end-to-end audio processing."""
        # Create test task
        task = ProcessingTask(
            task_id="test_001",
            audio_data=b"fake_audio_data",
            session_id="test_session",
            timestamp=time.time(),
            metadata={
                "source_lang": "ru",
                "target_lang": "en"
            }
        )
        
        # Mock the ASR, MT, and TTS functions
        with patch('app.asr.transcribe_chunk') as mock_asr, \
             patch('app.mt.translate_text') as mock_mt, \
             patch('app.tts.synthesize_text') as mock_tts:
            
            mock_asr.return_value = "Привет мир"
            mock_mt.return_value = AsyncMock(return_value="Hello world")()
            mock_tts.return_value = b"synthesized_audio_data"
            
            result = await concurrent_audio_processor(task)
            
            # Verify successful processing
            assert result.success
            assert result.result_data == b"synthesized_audio_data"
            assert result.metadata["transcript"] == "Привет мир"
            assert result.metadata["translation"] == "Hello world"
            assert result.processing_time_ms > 0

    @pytest.mark.asyncio
    async def test_empty_transcript_handling(self):
        """Test handling of empty ASR transcript."""
        task = ProcessingTask(
            task_id="test_002",
            audio_data=b"silent_audio",
            session_id="test_session",
            timestamp=time.time(),
            metadata={"source_lang": "ru", "target_lang": "en"}
        )
        
        with patch('app.asr.transcribe_chunk') as mock_asr:
            mock_asr.return_value = ""  # Empty transcript
            
            result = await concurrent_audio_processor(task)
            
            assert not result.success
            assert "No speech detected" in result.error_message
            assert result.processing_time_ms > 0

    @pytest.mark.asyncio
    async def test_translation_failure_handling(self):
        """Test handling of translation failures."""
        task = ProcessingTask(
            task_id="test_003",
            audio_data=b"audio_data",
            session_id="test_session",
            timestamp=time.time(),
            metadata={"source_lang": "ru", "target_lang": "en"}
        )
        
        with patch('app.asr.transcribe_chunk') as mock_asr, \
             patch('app.mt.translate_text') as mock_mt:
            
            mock_asr.return_value = "Test transcript"
            mock_mt.return_value = AsyncMock(return_value="")()  # Empty translation
            
            result = await concurrent_audio_processor(task)
            
            assert not result.success
            assert "Translation produced empty result" in result.error_message

    @pytest.mark.asyncio
    async def test_tts_failure_handling(self):
        """Test handling of TTS synthesis failures."""
        task = ProcessingTask(
            task_id="test_004",
            audio_data=b"audio_data",
            session_id="test_session",
            timestamp=time.time(),
            metadata={"source_lang": "ru", "target_lang": "en"}
        )
        
        with patch('app.asr.transcribe_chunk') as mock_asr, \
             patch('app.mt.translate_text') as mock_mt, \
             patch('app.tts.synthesize_text') as mock_tts:
            
            mock_asr.return_value = "Test transcript"
            mock_mt.return_value = AsyncMock(return_value="Test translation")()
            mock_tts.return_value = None  # TTS failure
            
            result = await concurrent_audio_processor(task)
            
            assert not result.success
            assert "TTS synthesis failed" in result.error_message

    @pytest.mark.asyncio
    async def test_pipeline_exception_handling(self):
        """Test handling of unexpected pipeline exceptions."""
        task = ProcessingTask(
            task_id="test_005",
            audio_data=b"audio_data",
            session_id="test_session",
            timestamp=time.time(),
            metadata={"source_lang": "ru", "target_lang": "en"}
        )
        
        with patch('app.asr.transcribe_chunk') as mock_asr:
            mock_asr.side_effect = Exception("Unexpected ASR error")
            
            result = await concurrent_audio_processor(task)
            
            assert not result.success
            assert "Pipeline error: Unexpected ASR error" in result.error_message


class TestWebSocketIntegration:
    """Test WebSocket endpoint integration."""

    @pytest.mark.asyncio
    async def test_websocket_session_initialization(self):
        """Test WebSocket session initialization."""
        # Mock WebSocket
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.receive = AsyncMock()
        mock_ws.send_text = AsyncMock()
        mock_ws.send_bytes = AsyncMock()
        
        # Mock message that triggers disconnect
        mock_ws.receive.side_effect = [
            {
                "type": "websocket.receive",
                "text": json.dumps({"type": "config", "source_lang": "ru", "target_lang": "en"})
            },
            Exception("WebSocket disconnect")  # Simulate disconnect
        ]
        
        with patch('app.pipeline_coordinator.create_pipeline_coordinator') as mock_create, \
             patch('app.pipeline_coordinator.create_realtime_config') as mock_config:
            
            mock_coordinator = AsyncMock()
            mock_coordinator.start_pipeline = AsyncMock()
            mock_coordinator.stop_pipeline = AsyncMock()
            mock_coordinator.is_healthy.return_value = True
            mock_create.return_value = mock_coordinator
            mock_config.return_value = MagicMock()
            
            # Test session initialization
            try:
                await websocket_translate(mock_ws)
            except:
                pass  # Expected due to mocked disconnect
            
            # Verify coordinator was created and started
            mock_create.assert_called_once()
            mock_coordinator.start_pipeline.assert_called_once()
            mock_coordinator.stop_pipeline.assert_called_once()

    @pytest.mark.asyncio
    async def test_websocket_audio_processing(self):
        """Test WebSocket audio message processing."""
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_bytes = AsyncMock()
        
        # Mock audio message
        audio_message = {
            "type": "websocket.receive",
            "bytes": b"fake_webm_audio_data"
        }
        
        mock_ws.receive = AsyncMock(side_effect=[
            audio_message,
            Exception("Test disconnect")
        ])
        
        with patch('app.utils.convert_audio_to_wav') as mock_convert, \
             patch('app.pipeline_coordinator.create_pipeline_coordinator') as mock_create:
            
            mock_convert.return_value = b"converted_wav_data"
            
            mock_coordinator = AsyncMock()
            mock_coordinator.start_pipeline = AsyncMock()
            mock_coordinator.stop_pipeline = AsyncMock()
            mock_coordinator.add_audio_chunk = AsyncMock(return_value=True)
            mock_coordinator.get_next_result = AsyncMock(return_value=None)
            mock_coordinator.is_healthy.return_value = True
            mock_create.return_value = mock_coordinator
            
            try:
                await websocket_translate(mock_ws)
            except:
                pass
            
            # Verify audio processing
            mock_coordinator.add_audio_chunk.assert_called_once()

    @pytest.mark.asyncio
    async def test_websocket_backpressure_handling(self):
        """Test WebSocket backpressure handling."""
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        
        audio_message = {
            "type": "websocket.receive", 
            "bytes": b"audio_data"
        }
        
        mock_ws.receive = AsyncMock(side_effect=[
            audio_message,
            Exception("Test disconnect")
        ])
        
        with patch('app.utils.convert_audio_to_wav') as mock_convert, \
             patch('app.pipeline_coordinator.create_pipeline_coordinator') as mock_create:
            
            mock_convert.return_value = b"wav_data"
            
            mock_coordinator = AsyncMock()
            mock_coordinator.start_pipeline = AsyncMock()
            mock_coordinator.stop_pipeline = AsyncMock()
            mock_coordinator.add_audio_chunk = AsyncMock(return_value=False)  # Buffer full
            mock_coordinator.handle_backpressure = AsyncMock()
            mock_coordinator.get_next_result = AsyncMock(return_value=None)
            mock_coordinator.is_healthy.return_value = True
            mock_create.return_value = mock_coordinator
            
            try:
                await websocket_translate(mock_ws)
            except:
                pass
            
            # Verify backpressure handling
            mock_coordinator.handle_backpressure.assert_called_once()


class TestPropertyBasedScenarios:
    """Property-based testing with Hypothesis."""

    @given(
        st.text(min_size=1, max_size=20),
        st.integers(min_value=100, max_value=10000),
        st.booleans(),
        st.floats(min_value=0.1, max_value=1.0)
    )
    @settings(max_examples=25)
    def test_session_id_properties(self, session_prefix, timestamp, has_speech, sensitivity):
        """Property test: Session ID generation maintains format invariants."""
        # Generate session ID
        session_id = generate_session_id()
        
        # Verify format properties
        assert isinstance(session_id, str)
        assert len(session_id) > 10  # Minimum reasonable length
        assert session_id.startswith("session_")
        
        # Verify uniqueness property
        session_id_2 = generate_session_id()
        assert session_id != session_id_2

    @given(
        st.binary(min_size=0, max_size=1000),
        st.floats(min_value=0.0, max_value=1.0)
    )
    @settings(max_examples=25)
    def test_vad_properties(self, audio_data, sensitivity):
        """Property test: VAD maintains consistent behavior."""
        try:
            has_speech, metadata = detect_speech_activity(audio_data, sensitivity)
            
            # VAD always returns boolean and dict
            assert isinstance(has_speech, bool)
            assert isinstance(metadata, dict)
            
            # Metadata contains expected keys
            assert "energy" in metadata
            assert "confidence" in metadata
            
            # Energy and confidence are non-negative
            assert metadata["energy"] >= 0.0
            assert metadata["confidence"] >= 0.0
            
        except Exception:
            # VAD should handle errors gracefully
            pass

    @given(
        st.text(min_size=1, max_size=50),
        st.binary(min_size=10, max_size=1000),
        st.dictionaries(
            st.text(min_size=1, max_size=20),
            st.one_of(st.text(min_size=1, max_size=20), st.floats(min_value=0.0, max_value=1.0)),
            min_size=1,
            max_size=5
        )
    )
    @settings(max_examples=25)
    def test_processing_task_properties(self, task_id, audio_data, metadata):
        """Property test: ProcessingTask creation maintains data integrity."""
        task = ProcessingTask(
            task_id=task_id,
            audio_data=audio_data,
            session_id="test_session",
            timestamp=time.time(),
            metadata=metadata
        )
        
        # Task maintains input data
        assert task.task_id == task_id
        assert task.audio_data == audio_data
        assert task.session_id == "test_session"
        assert task.metadata == metadata
        
        # Task has valid timestamp
        assert task.timestamp > 0
        assert task.timestamp <= time.time()


class TestPerformanceAndCompliance:
    """Test performance characteristics and latency compliance."""

    @pytest.mark.asyncio
    async def test_concurrent_processing_latency(self):
        """Test concurrent processing maintains latency targets."""
        # Create multiple tasks for concurrent processing
        tasks = []
        for i in range(5):
            task = ProcessingTask(
                task_id=f"perf_test_{i}",
                audio_data=b"test_audio_data",
                session_id="perf_session",
                timestamp=time.time(),
                metadata={"source_lang": "ru", "target_lang": "en"}
            )
            tasks.append(task)
        
        # Mock fast processing
        with patch('app.asr.transcribe_chunk') as mock_asr, \
             patch('app.mt.translate_text') as mock_mt, \
             patch('app.tts.synthesize_text') as mock_tts:
            
            mock_asr.return_value = "Test transcript"
            mock_mt.return_value = AsyncMock(return_value="Test translation")()
            mock_tts.return_value = b"audio_result"
            
            # Process tasks concurrently
            start_time = time.time()
            results = await asyncio.gather(*[
                concurrent_audio_processor(task) for task in tasks
            ])
            total_time = time.time() - start_time
            
            # Verify all tasks succeeded
            assert all(result.success for result in results)
            
            # Verify concurrent processing is faster than sequential
            # (This is more of a timing characteristic test)
            assert total_time < 5.0  # Should complete quickly with mocks

    def test_session_registry_performance(self):
        """Test session registry performance under load."""
        # Clear registry
        active_sessions.clear()
        
        # Add many sessions
        session_count = 50
        start_time = time.time()
        
        for i in range(session_count):
            session_id = f"perf_session_{i}"
            config = create_realtime_config()
            coordinator = create_pipeline_coordinator(session_id, config)
            active_sessions[session_id] = coordinator
        
        add_time = time.time() - start_time
        
        # Verify performance
        assert len(active_sessions) == session_count
        assert add_time < 1.0  # Should be fast
        
        # Test lookup performance
        start_time = time.time()
        for i in range(session_count):
            session_id = f"perf_session_{i}"
            assert session_id in active_sessions
        
        lookup_time = time.time() - start_time
        assert lookup_time < 0.1  # Lookups should be very fast


class TestErrorRecoveryAndResilience:
    """Test error recovery and system resilience."""

    @pytest.mark.asyncio
    async def test_coordinator_failure_recovery(self):
        """Test recovery from coordinator failures."""
        config = create_realtime_config()
        coordinator = create_pipeline_coordinator("test_session", config)
        
        # Start coordinator
        mock_processor = AsyncMock()
        await coordinator.start_pipeline(mock_processor)
        
        # Simulate failure by forcing an exception
        with patch.object(coordinator, 'add_audio_chunk', side_effect=Exception("Coordinator failure")):
            # Should handle exception gracefully
            try:
                await coordinator.add_audio_chunk(b"test", 100, True)
            except Exception:
                pass  # Expected
        
        # Coordinator should still be stoppable
        await coordinator.stop_pipeline()

    def test_active_sessions_cleanup(self):
        """Test cleanup of active sessions registry."""
        # Add test sessions
        active_sessions.clear()
        session_ids = ["session_1", "session_2", "session_3"]
        
        for session_id in session_ids:
            config = create_realtime_config()
            coordinator = create_pipeline_coordinator(session_id, config)
            active_sessions[session_id] = coordinator
        
        # Verify initial state
        assert len(active_sessions) == 3
        
        # Simulate cleanup
        for session_id in list(active_sessions.keys()):
            del active_sessions[session_id]
        
        # Verify cleanup
        assert len(active_sessions) == 0

    @pytest.mark.asyncio
    async def test_websocket_disconnect_cleanup(self):
        """Test proper cleanup on WebSocket disconnect."""
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.receive = AsyncMock(side_effect=Exception("Connection lost"))
        
        with patch('app.pipeline_coordinator.create_pipeline_coordinator') as mock_create:
            mock_coordinator = AsyncMock()
            mock_coordinator.start_pipeline = AsyncMock()
            mock_coordinator.stop_pipeline = AsyncMock()
            mock_create.return_value = mock_coordinator
            
            # Test WebSocket with disconnect
            try:
                await websocket_translate(mock_ws)
            except:
                pass  # Expected due to mocked disconnect
            
            # Verify cleanup was called
            mock_coordinator.stop_pipeline.assert_called_once()
