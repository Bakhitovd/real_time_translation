"""
Comprehensive tests for Module 7: M2M-100 Translation Service
Tests GPU-optimized translation service with session-based context management.
Target: ≥90% coverage, ≥25 random test cases with hypothesis.
"""

import asyncio
import pytest
import time
from unittest.mock import Mock, patch, AsyncMock
from collections import deque
from typing import Dict, Any
import torch
from hypothesis import given, strategies as st, settings
from fastapi.testclient import TestClient
from app.m2m_service import (
    SessionContext, M2MTranslationService, TranslationRequest, 
    TranslationResponse, app, service
)


class TestSessionContext:
    """Test session context management with property-based testing."""
    
    def setup_method(self):
        """Setup mock tokenizer for testing."""
        self.mock_tokenizer = Mock()
        self.mock_tokenizer.encode.side_effect = lambda text: list(range(len(text.split())))
    
    def test_session_context_initialization(self):
        """Test SessionContext initialization with correct defaults."""
        context = SessionContext()
        assert len(context.buffer) == 0
        assert context.token_count == 0
        assert isinstance(context.last_access, float)
        assert context.buffer.maxlen == 3
    
    @given(st.text(min_size=1, max_size=100).filter(lambda x: x.strip()))
    def test_add_text_single(self, text):
        """Property test: Adding single text updates context correctly."""
        context = SessionContext()
        initial_time = context.last_access
        
        # Wait to ensure time difference
        time.sleep(0.01)
        context.add_text(text, self.mock_tokenizer)
        
        assert len(context.buffer) == 1
        assert context.buffer[0] == text.strip()
        assert context.last_access > initial_time
        assert context.token_count == len(text.strip().split())
    
    @given(st.lists(st.text(min_size=1, max_size=50).filter(lambda x: x.strip()), min_size=1, max_size=10))
    def test_add_multiple_texts(self, texts):
        """Property test: Adding multiple texts maintains buffer constraints."""
        context = SessionContext()
        
        for text in texts:
            context.add_text(text, self.mock_tokenizer)
        
        # Buffer should not exceed maxlen=3
        assert len(context.buffer) <= 3
        
        # Should contain last texts added (up to 3), stripped
        expected_texts = [t.strip() for t in texts[-3:] if t.strip()] if len(texts) >= 3 else [t.strip() for t in texts if t.strip()]
        assert list(context.buffer) == expected_texts
        
        # Token count should be sum of last texts in buffer
        expected_tokens = sum(len(text.split()) for text in expected_texts)
        assert context.token_count == expected_tokens
    
    def test_add_empty_text(self):
        """Test adding empty text doesn't modify context."""
        context = SessionContext()
        initial_time = context.last_access
        
        context.add_text("", self.mock_tokenizer)
        context.add_text("   ", self.mock_tokenizer)
        
        assert len(context.buffer) == 0
        assert context.token_count == 0
        assert context.last_access == initial_time
    
    def test_token_limit_truncation(self):
        """Test context truncation when exceeding 1k token limit."""
        context = SessionContext()
        
        # Mock tokenizer to return high token counts
        self.mock_tokenizer.encode.side_effect = lambda text: list(range(600))  # 600 tokens per text
        
        # Add two texts (1200 tokens total, exceeds 1000 limit)
        context.add_text("first long text", self.mock_tokenizer)
        context.add_text("second long text", self.mock_tokenizer)
        
        # Should truncate first text to stay under limit
        assert len(context.buffer) == 1
        assert context.buffer[0] == "second long text"
        assert context.token_count == 600
    
    @given(st.lists(st.text(min_size=1, max_size=20).filter(lambda x: x.strip()), min_size=0, max_size=5))
    def test_get_context(self, texts):
        """Property test: get_context returns properly formatted string."""
        context = SessionContext()
        
        for text in texts:
            context.add_text(text, self.mock_tokenizer)
        
        result = context.get_context()
        
        if texts:
            expected_texts = [t.strip() for t in texts[-3:] if t.strip()] if len(texts) >= 3 else [t.strip() for t in texts if t.strip()]
            expected = " ".join(expected_texts)
            assert result == expected
        else:
            assert result == ""


class TestM2MTranslationService:
    """Test M2M-100 translation service with mocked dependencies."""
    
    def setup_method(self):
        """Setup service with mocked model dependencies."""
        self.service = M2MTranslationService("test-model")
    
    def test_service_initialization(self):
        """Test service initializes with correct parameters."""
        assert self.service.model_name == "test-model"
        assert self.service.device in ["cuda", "cpu"]
        assert self.service.model is None
        assert self.service.tokenizer is None
        assert len(self.service.session_contexts) == 0
        assert self.service.translation_count == 0
        assert self.service.total_latency == 0.0
    
    @pytest.mark.asyncio
    @patch('app.m2m_service.M2M100Tokenizer')
    @patch('app.m2m_service.M2M100ForConditionalGeneration')
    @patch('torch.cuda.is_available', return_value=True)
    @patch('torch.cuda.get_device_name', return_value="Test GPU")
    async def test_initialize_with_gpu(self, mock_device_name, mock_cuda, mock_model_class, mock_tokenizer_class):
        """Test service initialization with GPU."""
        # Create service after mocking cuda availability
        service = M2MTranslationService("test-model")
        
        # Setup mocks
        mock_tokenizer = Mock()
        mock_model = Mock()
        mock_tokenizer_class.from_pretrained.return_value = mock_tokenizer
        mock_model_class.from_pretrained.return_value = mock_model
        
        await service.initialize()
        
        assert service.tokenizer == mock_tokenizer
        assert service.model == mock_model.cuda.return_value  # Model gets wrapped by .cuda()
        assert service.device == "cuda"
        mock_model.cuda.assert_called_once()
        mock_model.cuda.return_value.eval.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('app.m2m_service.M2M100Tokenizer')
    @patch('app.m2m_service.M2M100ForConditionalGeneration')
    @patch('torch.cuda.is_available', return_value=False)
    async def test_initialize_cpu_fallback(self, mock_cuda, mock_model_class, mock_tokenizer_class):
        """Test service initialization with CPU fallback."""
        mock_tokenizer = Mock()
        mock_model = Mock()
        mock_tokenizer_class.from_pretrained.return_value = mock_tokenizer
        mock_model_class.from_pretrained.return_value = mock_model
        
        await self.service.initialize()
        
        assert self.service.device == "cpu"
        mock_model.cuda.assert_not_called()
    
    @pytest.mark.asyncio
    @patch('app.m2m_service.M2M100Tokenizer')
    @patch('app.m2m_service.M2M100ForConditionalGeneration')
    async def test_initialize_failure(self, mock_model_class, mock_tokenizer_class):
        """Test service initialization handles failures."""
        mock_tokenizer_class.from_pretrained.side_effect = Exception("Model load failed")
        
        with pytest.raises(Exception, match="Model load failed"):
            await self.service.initialize()
    
    @pytest.mark.asyncio
    async def test_translate_without_initialization(self):
        """Test translation fails when service not initialized."""
        from fastapi import HTTPException
        
        with pytest.raises(HTTPException) as exc_info:
            await self.service.translate("test_session", "test text")
        
        assert exc_info.value.status_code == 503
        assert "not initialized" in str(exc_info.value.detail)
    
    @pytest.mark.asyncio
    @patch('app.m2m_service.torch.no_grad')
    @patch('app.m2m_service.time.time')
    async def test_translate_success(self, mock_time, mock_no_grad):
        """Test successful translation with context."""
        # Mock time to simulate latency - need values for start_time, context.add_text(), end_time
        mock_time.side_effect = [1000.0, 1000.05, 1000.1]  # start_time, context_time, end_time
        
        # Setup initialized service
        self.service.tokenizer = Mock()
        self.service.model = Mock()
        self.service.device = "cpu"
        
        # Mock tokenizer and model behavior
        self.service.tokenizer.encode.return_value = [1, 2, 3]
        self.service.tokenizer.return_value = {"input_ids": Mock(), "attention_mask": Mock()}
        self.service.tokenizer.get_lang_id.return_value = 123
        self.service.tokenizer.decode.return_value = "translated text"
        
        mock_outputs = Mock()
        self.service.model.generate.return_value = [mock_outputs]
        
        # Test translation
        translation, metadata = await self.service.translate(
            "test_session", "test text", "ru", "en", True
        )
        
        assert translation == "translated text"
        assert isinstance(metadata, dict)
        assert "latency_ms" in metadata
        assert "context_tokens" in metadata
        assert metadata["used_context"] is False  # No previous context
        assert self.service.translation_count == 1
        assert self.service.total_latency > 0
    
    def test_translate_property_based_sync(self):
        """Property test converted to sync: Translation handles various inputs correctly."""
        # Use a simple list of test cases instead of hypothesis for async compatibility
        test_cases = [
            ("hello world", "ru", "en"),
            ("test text", "en", "ru"),
            ("sample input", "fr", "de"),
        ]
        
        for text, source_lang, target_lang in test_cases:
            # Setup mocked initialized service
            service = M2MTranslationService("test-model")
            service.tokenizer = Mock()
            service.model = Mock()
            service.device = "cpu"
            
            service.tokenizer.encode.return_value = [1, 2, 3]
            service.tokenizer.return_value = {"input_ids": Mock(), "attention_mask": Mock()}
            service.tokenizer.get_lang_id.return_value = 123
            service.tokenizer.decode.return_value = f"translated: {text}"
            
            mock_outputs = Mock()
            service.model.generate.return_value = [mock_outputs]
            
            session_id = f"session_{hash(text) % 1000}"
            
            # Run async function synchronously
            translation, metadata = asyncio.run(service.translate(
                session_id, text, source_lang, target_lang, True
            ))
            
            assert isinstance(translation, str)
            assert len(translation) > 0
            assert isinstance(metadata, dict)
            assert metadata["input_length"] == len(text)
            assert metadata["source_lang"] == source_lang
            assert metadata["target_lang"] == target_lang
    
    def test_cleanup_session_exists(self):
        """Test cleanup of existing session."""
        # Add a session context
        self.service.session_contexts["test_session"] = SessionContext()
        
        result = self.service.cleanup_session("test_session")
        
        assert result is True
        assert "test_session" not in self.service.session_contexts
    
    def test_cleanup_session_not_exists(self):
        """Test cleanup of non-existent session."""
        result = self.service.cleanup_session("nonexistent_session")
        assert result is False
    
    def test_cleanup_stale_sessions(self):
        """Test cleanup of stale sessions based on age."""
        # Add sessions with different ages
        old_context = SessionContext()
        old_context.last_access = time.time() - 7200  # 2 hours ago
        
        new_context = SessionContext()
        new_context.last_access = time.time() - 1800  # 30 minutes ago
        
        self.service.session_contexts["old_session"] = old_context
        self.service.session_contexts["new_session"] = new_context
        
        # Cleanup sessions older than 1 hour
        cleaned = self.service.cleanup_stale_sessions(3600)
        
        assert cleaned == 1
        assert "old_session" not in self.service.session_contexts
        assert "new_session" in self.service.session_contexts
    
    @given(st.integers(min_value=0, max_value=1000), st.floats(min_value=0.0, max_value=10000.0))
    def test_get_service_stats(self, translation_count, total_latency):
        """Property test: Service stats calculation is correct."""
        self.service.translation_count = translation_count
        self.service.total_latency = total_latency
        
        # Add some session contexts
        for i in range(3):
            self.service.session_contexts[f"session_{i}"] = SessionContext()
        
        stats = self.service.get_service_stats()
        
        assert stats["translations_completed"] == translation_count
        assert stats["active_sessions"] == 3
        assert isinstance(stats["gpu_available"], bool)
        assert isinstance(stats["model_loaded"], bool)
        
        if translation_count > 0:
            expected_avg = total_latency / translation_count
            assert abs(stats["average_latency_ms"] - expected_avg) < 0.001
            assert stats["target_compliance"] == (expected_avg < 200.0)
        else:
            assert stats["average_latency_ms"] == 0.0
            assert stats["target_compliance"] is True


class TestAPIEndpoints:
    """Test FastAPI endpoints with mocked service."""
    
    def setup_method(self):
        """Setup test client."""
        self.client = TestClient(app)
    
    @pytest.mark.asyncio
    @patch.object(service, 'translate')
    async def test_translate_endpoint_success(self, mock_translate):
        """Test successful translation endpoint."""
        mock_translate.return_value = ("translated text", {"latency_ms": 150.0})
        
        response = self.client.post("/translate", json={
            "session_id": "test_session",
            "text": "test text",
            "source_lang": "ru",
            "target_lang": "en",
            "use_context": True
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["translation"] == "translated text"
        assert data["metadata"]["latency_ms"] == 150.0
    
    @patch.object(service, 'cleanup_session')
    def test_cleanup_session_endpoint(self, mock_cleanup):
        """Test session cleanup endpoint."""
        mock_cleanup.return_value = True
        
        response = self.client.delete("/sessions/test_session")
        
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "test_session"
        assert data["cleaned"] is True
    
    @patch.object(service, 'get_service_stats')
    def test_health_endpoint(self, mock_stats):
        """Test health check endpoint."""
        mock_stats.return_value = {
            "translations_completed": 100,
            "average_latency_ms": 180.0,
            "active_sessions": 5,
            "gpu_available": True,
            "model_loaded": True,
            "target_compliance": True
        }
        
        response = self.client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["translations_completed"] == 100
        assert data["average_latency_ms"] == 180.0
        assert data["target_compliance"] is True
    
    @patch.object(service, 'cleanup_stale_sessions')
    def test_cleanup_stale_endpoint(self, mock_cleanup_stale):
        """Test stale session cleanup endpoint."""
        mock_cleanup_stale.return_value = 3
        
        response = self.client.post("/cleanup", params={"max_age_seconds": 1800})
        
        assert response.status_code == 200
        data = response.json()
        assert data["cleaned_sessions"] == 3


class TestIntegrationScenarios:
    """Integration tests for realistic usage scenarios."""
    
    def setup_method(self):
        """Setup service for integration testing."""
        self.service = M2MTranslationService()
        # Mock initialization without actual model loading
        self.service.tokenizer = Mock()
        self.service.model = Mock()
        self.service.device = "cpu"
        
        # Setup realistic mock responses
        self.service.tokenizer.encode.side_effect = lambda text: list(range(len(text.split())))
        self.service.tokenizer.return_value = {"input_ids": Mock(), "attention_mask": Mock()}
        self.service.tokenizer.get_lang_id.return_value = 123
        self.service.tokenizer.decode.side_effect = lambda outputs, **kwargs: f"translated: {outputs}"
        
        mock_outputs = Mock()
        self.service.model.generate.return_value = [mock_outputs]
    
    @pytest.mark.asyncio
    async def test_multi_session_context_isolation(self):
        """Test that different sessions maintain isolated contexts."""
        # Session 1: Add some context
        await self.service.translate("session1", "First sentence", "ru", "en")
        await self.service.translate("session1", "Second sentence", "ru", "en")
        
        # Session 2: Add different context
        await self.service.translate("session2", "Different first", "ru", "en")
        
        # Verify context isolation
        session1_context = self.service.session_contexts["session1"].get_context()
        session2_context = self.service.session_contexts["session2"].get_context()
        
        assert "First sentence Second sentence" in session1_context
        assert "Different first" in session2_context
        assert "Different first" not in session1_context
        assert "First sentence" not in session2_context
    
    @pytest.mark.asyncio
    @patch('app.m2m_service.time.time')
    async def test_performance_tracking_accuracy(self, mock_time):
        """Test that performance metrics are tracked accurately."""
        # Mock time to simulate latency - need enough values for all time.time() calls
        # Each translation calls time.time() twice (start and end), plus context.add_text calls it once
        times = []
        base_time = 1000.0
        for i in range(20):  # More than enough for 5 translations
            times.append(base_time + i * 0.1)
        mock_time.side_effect = times
        
        initial_count = self.service.translation_count
        initial_latency = self.service.total_latency
        
        # Perform multiple translations
        for i in range(5):
            await self.service.translate(f"session_{i}", f"text {i}", "ru", "en")
        
        assert self.service.translation_count == initial_count + 5
        assert self.service.total_latency > initial_latency
        
        stats = self.service.get_service_stats()
        assert stats["translations_completed"] == initial_count + 5
        assert stats["average_latency_ms"] > 0
    
    def test_session_lifecycle_management(self):
        """Test complete session lifecycle from creation to cleanup."""
        session_id = "lifecycle_test_session"
        
        # Verify session doesn't exist initially
        assert session_id not in self.service.session_contexts
        
        # Create session implicitly through translation
        asyncio.run(self.service.translate(session_id, "test text", "ru", "en"))
        
        # Verify session exists
        assert session_id in self.service.session_contexts
        
        # Cleanup session
        result = self.service.cleanup_session(session_id)
        
        # Verify cleanup
        assert result is True
        assert session_id not in self.service.session_contexts


# Simplified performance tests without external benchmark plugins
class TestBasicPerformance:
    """Basic performance tests for development feedback."""
    
    def test_context_operations_basic(self):
        """Basic performance test for context operations."""
        context = SessionContext()
        mock_tokenizer = Mock()
        mock_tokenizer.encode.side_effect = lambda text: list(range(len(text.split())))
        
        start_time = time.time()
        for i in range(100):
            context.add_text(f"test sentence {i}", mock_tokenizer)
            context.get_context()
        duration = time.time() - start_time
        
        # Should complete within reasonable time (less than 1 second)
        assert duration < 1.0
        assert len(context.buffer) <= 3  # Buffer constraint maintained


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--cov=app.m2m_service", "--cov-report=term-missing"])
