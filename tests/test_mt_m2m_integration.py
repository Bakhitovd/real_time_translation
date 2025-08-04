"""
Unit tests for M2M-100 service integration in MT module.
Tests service connectivity, request/response validation, session management, and error handling.
"""

import pytest
import asyncio
import time
import httpx
from unittest.mock import AsyncMock, patch, MagicMock
from app.mt import StreamingMT, get_mt_instance, translate_text


class TestStreamingMT:
    """Test M2M-100 StreamingMT class functionality."""
    
    @pytest.fixture
    def mt_service(self):
        """Create StreamingMT instance for testing."""
        return StreamingMT(service_url="http://localhost:8001", timeout_seconds=5.0)
    
    def test_init_with_config(self, mt_service):
        """Test M2M service initialization with configuration."""
        assert mt_service.service_url == "http://localhost:8001"
        assert mt_service.timeout_seconds == 5.0
        assert mt_service.max_retries == 3
        assert mt_service.failure_count == 0
        assert mt_service.circuit_open_duration == 60
    
    def test_circuit_breaker_closed_initially(self, mt_service):
        """Test circuit breaker is closed on initialization."""
        assert not mt_service._is_circuit_open()
    
    def test_circuit_breaker_opens_after_failures(self, mt_service):
        """Test circuit breaker opens after multiple failures."""
        mt_service.failure_count = 3
        mt_service.last_failure_time = time.time()
        assert mt_service._is_circuit_open()
    
    def test_circuit_breaker_resets_after_timeout(self, mt_service):
        """Test circuit breaker resets after timeout period."""
        mt_service.failure_count = 3
        mt_service.last_failure_time = time.time() - 70  # 70 seconds ago
        assert not mt_service._is_circuit_open()
        assert mt_service.failure_count == 0
    
    @pytest.mark.asyncio
    async def test_successful_translation(self, mt_service):
        """Test successful M2M translation request."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "translation": "Hello, how are you?",
            "metadata": {"latency_ms": 150.0}
        }
        mock_response.raise_for_status = MagicMock()
        
        with patch.object(mt_service.http_client, 'post', return_value=mock_response) as mock_post:
            result = await mt_service.translate_text("Привет, как дела?", "ru", "en", "test_session")
            
            assert result == "Hello, how are you?"
            mock_post.assert_called_once()
            
            # Verify request payload
            call_args = mock_post.call_args
            payload = call_args[1]['json']
            assert payload['session_id'] == "test_session"
            assert payload['text'] == "Привет, как дела?"
            assert payload['source_lang'] == "ru"
            assert payload['target_lang'] == "en"
            assert payload['use_context'] is True
    
    @pytest.mark.asyncio
    async def test_empty_text_translation(self, mt_service):
        """Test translation with empty text returns empty string."""
        result = await mt_service.translate_text("", "ru", "en", "test_session")
        assert result == ""
        
        result = await mt_service.translate_text("   ", "ru", "en", "test_session")
        assert result == ""
    
    @pytest.mark.asyncio
    async def test_network_timeout_retry(self, mt_service):
        """Test retry mechanism on network timeout."""
        with patch.object(mt_service.http_client, 'post') as mock_post:
            # First two calls timeout, third succeeds
            mock_post.side_effect = [
                httpx.ConnectTimeout("Connection timeout"),
                httpx.ReadTimeout("Read timeout"),
                MagicMock(json=lambda: {"translation": "Success"}, raise_for_status=MagicMock())
            ]
            
            result = await mt_service.translate_text("test", "ru", "en", "test_session")
            
            assert result == "Success"
            assert mock_post.call_count == 3
            assert mt_service.failure_count == 0  # Success resets failure count
    
    @pytest.mark.asyncio
    async def test_all_retries_fail(self, mt_service):
        """Test behavior when all retries fail."""
        with patch.object(mt_service.http_client, 'post') as mock_post:
            mock_post.side_effect = httpx.ConnectTimeout("Connection timeout")
            
            result = await mt_service.translate_text("test", "ru", "en", "test_session")
            
            # Should return original text when all retries fail
            assert result == "test"
            assert mock_post.call_count == 3  # max_retries
            assert mt_service.failure_count == 1  # Circuit breaker updated
    
    @pytest.mark.asyncio
    async def test_http_status_error_handling(self, mt_service):
        """Test handling of HTTP status errors."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        
        with patch.object(mt_service.http_client, 'post') as mock_post:
            mock_post.side_effect = httpx.HTTPStatusError("Server error", request=MagicMock(), response=mock_response)
            
            result = await mt_service.translate_text("test", "ru", "en", "test_session")
            
            assert result == "test"  # Return original on error
            assert mt_service.failure_count == 1
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_skips_translation(self, mt_service):
        """Test circuit breaker skips translation when open."""
        mt_service.failure_count = 3
        mt_service.last_failure_time = time.time()
        
        with patch.object(mt_service.http_client, 'post') as mock_post:
            result = await mt_service.translate_text("test", "ru", "en", "test_session")
            
            assert result == "test"  # Original text returned
            mock_post.assert_not_called()  # No HTTP request made
    
    @pytest.mark.asyncio
    async def test_service_health_check_success(self, mt_service):
        """Test successful service health check."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "translations_completed": 100,
            "average_latency_ms": 150.0,
            "model_loaded": True,
            "gpu_available": True
        }
        mock_response.raise_for_status = MagicMock()
        
        with patch.object(mt_service.http_client, 'get', return_value=mock_response) as mock_get:
            health = await mt_service.check_service_health()
            
            assert health["translations_completed"] == 100
            assert health["model_loaded"] is True
            mock_get.assert_called_once_with("http://localhost:8001/health", timeout=5.0)
    
    @pytest.mark.asyncio
    async def test_service_health_check_failure(self, mt_service):
        """Test service health check failure handling."""
        with patch.object(mt_service.http_client, 'get') as mock_get:
            mock_get.side_effect = httpx.ConnectError("Connection failed")
            
            health = await mt_service.check_service_health()
            
            assert "error" in health
            assert health["healthy"] is False
    
    @pytest.mark.asyncio
    async def test_cleanup_closes_client(self, mt_service):
        """Test cleanup properly closes HTTP client."""
        with patch.object(mt_service.http_client, 'aclose') as mock_close:
            await mt_service.cleanup()
            mock_close.assert_called_once()


class TestGlobalMTInstance:
    """Test global MT instance management."""
    
    def test_get_mt_instance_singleton(self):
        """Test global MT instance is singleton."""
        instance1 = get_mt_instance()
        instance2 = get_mt_instance()
        assert instance1 is instance2
    
    @pytest.mark.asyncio
    async def test_convenience_translate_function(self):
        """Test convenience translate_text function."""
        mock_instance = AsyncMock()
        mock_instance.translate_text.return_value = "translated"
        
        with patch('app.mt.get_mt_instance', return_value=mock_instance):
            result = await translate_text("test", "ru", "en", "session_123")
            
            assert result == "translated"
            mock_instance.translate_text.assert_called_once_with("test", "ru", "en", "session_123")


class TestConfigurationIntegration:
    """Test configuration loading and integration."""
    
    @pytest.mark.asyncio
    async def test_config_loading_from_yaml(self):
        """Test M2M service configuration is loaded from config.yaml."""
        mock_config = {
            "translation": {
                "m2m_service": {
                    "url": "http://custom:8002",
                    "timeout_seconds": 10.0,
                    "max_retries": 5
                }
            }
        }
        
        with patch('app.mt.load_config', return_value=mock_config):
            service = StreamingMT()
            
            assert service.service_url == "http://custom:8002"
            assert service.timeout_seconds == 10.0
            assert service.max_retries == 5
    
    def test_default_config_fallback(self):
        """Test default configuration when config is missing."""
        with patch('app.mt.load_config', return_value={}):
            service = StreamingMT()
            
            assert service.service_url == "http://localhost:8001"
            assert service.timeout_seconds == 5.0
            assert service.max_retries == 3


# Property-based testing with hypothesis
try:
    from hypothesis import given, strategies as st
    
    class TestM2MPropertyBased:
        """Property-based tests for M2M integration."""
        
        @given(
            text=st.text(min_size=1, max_size=1000),
            source_lang=st.sampled_from(["ru", "en", "es", "fr", "de"]),
            target_lang=st.sampled_from(["ru", "en", "es", "fr", "de"]),
            session_id=st.text(min_size=1, max_size=50)
        )
        @pytest.mark.asyncio
        async def test_translation_request_structure(self, text, source_lang, target_lang, session_id):
            """Test translation request structure with random inputs."""
            service = StreamingMT()
            
            mock_response = MagicMock()
            mock_response.json.return_value = {"translation": f"translated_{text}"}
            mock_response.raise_for_status = MagicMock()
            
            with patch.object(service.http_client, 'post', return_value=mock_response) as mock_post:
                result = await service.translate_text(text, source_lang, target_lang, session_id)
                
                # Verify request structure
                call_args = mock_post.call_args
                payload = call_args[1]['json']
                
                assert payload['session_id'] == session_id
                assert payload['text'] == text
                assert payload['source_lang'] == source_lang
                assert payload['target_lang'] == target_lang
                assert payload['use_context'] is True
                assert result == f"translated_{text}"
        
        @given(
            failure_count=st.integers(min_value=0, max_value=10),
            time_offset=st.integers(min_value=-120, max_value=120)
        )
        def test_circuit_breaker_behavior(self, failure_count, time_offset):
            """Test circuit breaker behavior with random failure counts and times."""
            service = StreamingMT()
            service.failure_count = failure_count
            service.last_failure_time = asyncio.get_event_loop().time() + time_offset
            
            expected_open = failure_count >= 3 and time_offset > -60
            assert service._is_circuit_open() == expected_open

except ImportError:
    # Hypothesis not available, skip property-based tests
    pass
