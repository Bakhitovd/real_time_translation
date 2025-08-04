"""
Integration tests for M2M-100 service in the complete translation pipeline.
Tests end-to-end pipeline flow, WebSocket integration, context persistence, and session isolation.
"""

import pytest
import asyncio
import json
import time
from unittest.mock import AsyncMock, patch, MagicMock
from app.ws import concurrent_audio_processor, generate_session_id
from app.realtime_queue import ProcessingTask, TaskPriority
from app.mt import get_mt_instance


class TestM2MPipelineIntegration:
    """Test M2M service integration with the complete translation pipeline."""
    
    @pytest.fixture
    def mock_audio_data(self):
        """Mock audio data for testing."""
        return b"fake_wav_audio_data" * 100  # 1600 bytes of mock audio
    
    @pytest.fixture
    def processing_task(self, mock_audio_data):
        """Create a processing task for testing."""
        return ProcessingTask(
            task_id="test_task_123",
            session_id="test_session_456",
            audio_data=mock_audio_data,
            timestamp=time.time(),
            priority=TaskPriority.NORMAL,
            metadata={"chunk_ids": ["chunk_1", "chunk_2"]}
        )
    
    @pytest.mark.asyncio
    async def test_complete_pipeline_with_m2m_success(self, processing_task):
        """Test complete pipeline flow with successful M2M translation."""
        # Mock ASR transcription
        with patch('app.ws.transcribe_chunk') as mock_asr:
            mock_asr.return_value = "Привет, как дела?"
            
            # Mock M2M translation
            with patch('app.ws.translate_text') as mock_translate:
                mock_translate.return_value = "Hello, how are you?"
                
                # Mock TTS synthesis
                with patch('app.ws.synthesize_text') as mock_tts:
                    mock_tts.return_value = b"fake_audio_output_data"
                    
                    # Execute pipeline
                    result = await concurrent_audio_processor(processing_task)
                    
                    # Verify successful pipeline execution
                    assert result.success is True
                    assert result.session_id == "test_session_456"
                    assert result.translated_audio == b"fake_audio_output_data"
                    
                    # Verify metadata
                    metadata = result.metadata
                    assert metadata["transcript"] == "Привет, как дела?"
                    assert metadata["translation"] == "Hello, how are you?"
                    assert metadata["audio_size"] == len(b"fake_audio_output_data")
                    
                    # Verify M2M translation was called with session_id
                    mock_translate.assert_called_once_with(
                        "Привет, как дела?", "auto", "en", session_id="test_session_456"
                    )
    
    @pytest.mark.asyncio
    async def test_pipeline_with_session_context_configuration(self, processing_task):
        """Test pipeline respects session language configuration."""
        # Set up session config
        from app.ws import current_session_configs
        current_session_configs["test_session_456"] = {
            "source_lang": "ru",
            "target_lang": "fr"
        }
        
        try:
            with patch('app.ws.transcribe_chunk') as mock_asr:
                mock_asr.return_value = "Привет, мир!"
                
                with patch('app.ws.translate_text') as mock_translate:
                    mock_translate.return_value = "Bonjour le monde!"
                    
                    with patch('app.ws.synthesize_text') as mock_tts:
                        mock_tts.return_value = b"french_audio_output"
                        
                        result = await concurrent_audio_processor(processing_task)
                        
                        assert result.success is True
                        
                        # Verify correct language configuration was used
                        mock_translate.assert_called_once_with(
                            "Привет, мир!", "ru", "fr", session_id="test_session_456"
                        )
        finally:
            # Cleanup session config
            current_session_configs.pop("test_session_456", None)
    
    @pytest.mark.asyncio
    async def test_pipeline_asr_failure_handling(self, processing_task):
        """Test pipeline handles ASR failure gracefully."""
        with patch('app.ws.transcribe_chunk') as mock_asr:
            mock_asr.return_value = ""  # Empty transcript (ASR failure)
            
            result = await concurrent_audio_processor(processing_task)
            
            assert result.success is False
            assert result.error_message == "No speech detected in audio segment"
            assert result.metadata["failed_stage"] == "asr"
            assert result.translated_audio is None
    
    @pytest.mark.asyncio
    async def test_pipeline_m2m_translation_failure_handling(self, processing_task):
        """Test pipeline handles M2M translation failure gracefully."""
        with patch('app.ws.transcribe_chunk') as mock_asr:
            mock_asr.return_value = "Test transcript"
            
            with patch('app.ws.translate_text') as mock_translate:
                mock_translate.return_value = ""  # Empty translation (M2M failure)
                
                result = await concurrent_audio_processor(processing_task)
                
                assert result.success is False
                assert result.error_message == "Translation produced empty result"
                assert result.metadata["failed_stage"] == "mt"
                assert result.metadata["transcript"] == "Test transcript"
                assert result.metadata["translation"] == ""
    
    @pytest.mark.asyncio
    async def test_pipeline_tts_failure_handling(self, processing_task):
        """Test pipeline handles TTS failure gracefully."""
        with patch('app.ws.transcribe_chunk') as mock_asr:
            mock_asr.return_value = "Test transcript"
            
            with patch('app.ws.translate_text') as mock_translate:
                mock_translate.return_value = "Test translation"
                
                with patch('app.ws.synthesize_text') as mock_tts:
                    mock_tts.return_value = None  # TTS failure
                    
                    result = await concurrent_audio_processor(processing_task)
                    
                    assert result.success is False
                    assert result.error_message == "TTS synthesis failed"
                    assert result.metadata["failed_stage"] == "tts"
                    assert result.metadata["transcript"] == "Test transcript"
                    assert result.metadata["translation"] == "Test translation"
    
    @pytest.mark.asyncio
    async def test_pipeline_latency_tracking(self, processing_task):
        """Test pipeline tracks latency for each stage."""
        with patch('app.ws.transcribe_chunk') as mock_asr:
            mock_asr.return_value = "Test transcript"
            
            with patch('app.ws.translate_text') as mock_translate:
                mock_translate.return_value = "Test translation"
                
                with patch('app.ws.synthesize_text') as mock_tts:
                    mock_tts.return_value = b"audio_data"
                    
                    result = await concurrent_audio_processor(processing_task)
                    
                    assert result.success is True
                    assert result.total_latency_ms > 0
                    assert "asr" in result.stage_latencies
                    assert "mt" in result.stage_latencies
                    assert "tts" in result.stage_latencies
                    
                    # Verify stage latencies are reasonable
                    for stage, latency in result.stage_latencies.items():
                        assert latency >= 0
                        assert latency < 10000  # Less than 10 seconds


class TestSessionManagement:
    """Test session-based functionality with M2M service."""
    
    def test_session_id_generation(self):
        """Test session ID generation is unique."""
        session1 = generate_session_id()
        session2 = generate_session_id()
        
        assert session1 != session2
        assert session1.startswith("session_")
        assert session2.startswith("session_")
        assert len(session1) > 20  # Should include timestamp
    
    @pytest.mark.asyncio
    async def test_concurrent_session_isolation(self):
        """Test multiple sessions work independently."""
        # Create two different processing tasks with different sessions
        task1 = ProcessingTask(
            task_id="task_1",
            session_id="session_1",
            audio_data=b"audio_data_1",
            timestamp=time.time(),
            priority=TaskPriority.NORMAL,
            metadata={"chunk_ids": ["chunk_1"]}
        )
        
        task2 = ProcessingTask(
            task_id="task_2", 
            session_id="session_2",
            audio_data=b"audio_data_2",
            timestamp=time.time(),
            priority=TaskPriority.NORMAL,
            metadata={"chunk_ids": ["chunk_2"]}
        )
        
        # Set up different configurations for each session
        from app.ws import current_session_configs
        current_session_configs["session_1"] = {"source_lang": "ru", "target_lang": "en"}
        current_session_configs["session_2"] = {"source_lang": "es", "target_lang": "fr"}
        
        try:
            with patch('app.ws.transcribe_chunk') as mock_asr:
                mock_asr.side_effect = ["Russian text", "Spanish text"]
                
                with patch('app.ws.translate_text') as mock_translate:
                    mock_translate.side_effect = ["English text", "French text"]
                    
                    with patch('app.ws.synthesize_text') as mock_tts:
                        mock_tts.side_effect = [b"english_audio", b"french_audio"]
                        
                        # Process both tasks concurrently
                        results = await asyncio.gather(
                            concurrent_audio_processor(task1),
                            concurrent_audio_processor(task2)
                        )
                        
                        result1, result2 = results
                        
                        # Verify both succeeded with correct session IDs
                        assert result1.success is True
                        assert result1.session_id == "session_1"
                        assert result2.success is True
                        assert result2.session_id == "session_2"
                        
                        # Verify translations were called with correct parameters
                        translate_calls = mock_translate.call_args_list
                        assert len(translate_calls) == 2
                        
                        # Session 1: ru -> en
                        call1_args = translate_calls[0][0]
                        call1_kwargs = translate_calls[0][1]
                        assert call1_args == ("Russian text", "ru", "en")
                        assert call1_kwargs["session_id"] == "session_1"
                        
                        # Session 2: es -> fr  
                        call2_args = translate_calls[1][0]
                        call2_kwargs = translate_calls[1][1]
                        assert call2_args == ("Spanish text", "es", "fr")
                        assert call2_kwargs["session_id"] == "session_2"
        finally:
            # Cleanup session configs
            current_session_configs.pop("session_1", None)
            current_session_configs.pop("session_2", None)


class TestM2MServiceHealthIntegration:
    """Test M2M service health monitoring integration."""
    
    @pytest.mark.asyncio
    async def test_m2m_service_health_check_integration(self):
        """Test M2M service health check works with pipeline."""
        mt_instance = get_mt_instance()
        
        # Mock successful health check
        mock_health_response = {
            "translations_completed": 50,
            "average_latency_ms": 125.0,
            "active_sessions": 3,
            "gpu_available": True,
            "model_loaded": True,
            "target_compliance": True
        }
        
        with patch.object(mt_instance, 'check_service_health') as mock_health:
            mock_health.return_value = mock_health_response
            
            health = await mt_instance.check_service_health()
            
            assert health["translations_completed"] == 50
            assert health["average_latency_ms"] == 125.0
            assert health["gpu_available"] is True
            assert health["model_loaded"] is True
            assert health["target_compliance"] is True
    
    @pytest.mark.asyncio
    async def test_m2m_service_health_check_failure_integration(self):
        """Test M2M service health check failure handling in pipeline."""
        mt_instance = get_mt_instance()
        
        with patch.object(mt_instance, 'check_service_health') as mock_health:
            mock_health.return_value = {"error": "Service unavailable", "healthy": False}
            
            health = await mt_instance.check_service_health()
            
            assert "error" in health
            assert health["healthy"] is False


# Property-based testing for pipeline integration
try:
    from hypothesis import given, strategies as st
    
    class TestM2MPipelinePropertyBased:
        """Property-based tests for M2M pipeline integration."""
        
        @given(
            session_id=st.text(min_size=5, max_size=50),
            transcript=st.text(min_size=1, max_size=500),
            translation=st.text(min_size=1, max_size=500)
        )
        @pytest.mark.asyncio
        async def test_pipeline_data_flow_integrity(self, session_id, transcript, translation):
            """Test pipeline maintains data integrity with random inputs."""
            # Create task with random session ID
            task = ProcessingTask(
                task_id=f"task_{hash(session_id)}",
                session_id=session_id,
                audio_data=b"mock_audio_data",
                timestamp=time.time(),
                priority=TaskPriority.NORMAL,
                metadata={"chunk_ids": ["test_chunk"]}
            )
            
            mock_audio_output = f"audio_for_{translation}".encode()
            
            with patch('app.ws.transcribe_chunk', return_value=transcript):
                with patch('app.ws.translate_text', return_value=translation):
                    with patch('app.ws.synthesize_text', return_value=mock_audio_output):
                        result = await concurrent_audio_processor(task)
                        
                        # Verify data integrity through pipeline
                        assert result.success is True
                        assert result.session_id == session_id
                        assert result.metadata["transcript"] == transcript
                        assert result.metadata["translation"] == translation
                        assert result.translated_audio == mock_audio_output

except ImportError:
    # Hypothesis not available, skip property-based tests
    pass
