"""
Tests for StreamingPipelineCoordinator module.

Comprehensive test suite with property-based testing and ≥90% coverage.
"""

import asyncio
import pytest
from unittest.mock import Mock, AsyncMock, patch
from dataclasses import asdict
from hypothesis import given, strategies as st

from app.pipeline_coordinator import (
    StreamingPipelineCoordinator, PipelineConfig, PipelineResult, CoordinatorStats,
    create_pipeline_coordinator, create_realtime_config, PipelineStage
)
from app.realtime_queue import ProcessingTask, TaskPriority


class TestPipelineConfig:
    """Test pipeline configuration dataclass."""
    
    def test_default_config_valid(self):
        """Test default configuration is valid."""
        config = PipelineConfig()
        assert config.max_buffer_duration_ms == 4000
        assert config.chunk_size_ms == 800
        assert config.target_latency_ms == 2000.0
        assert config.enable_parallelization is True
    
    def test_config_validation_negative_target_latency(self):
        """Test config validation rejects negative target latency."""
        with pytest.raises(ValueError, match="target_latency_ms must be positive"):
            PipelineConfig(target_latency_ms=-100.0)
    
    def test_config_validation_zero_chunk_size(self):
        """Test config validation rejects zero chunk size."""
        with pytest.raises(ValueError, match="chunk_size_ms must be positive"):
            PipelineConfig(chunk_size_ms=0)
    
    @given(st.floats(min_value=0.1, max_value=10000.0))
    def test_config_valid_target_latency(self, target_latency):
        """Property test: valid target latency values."""
        config = PipelineConfig(target_latency_ms=target_latency)
        assert config.target_latency_ms == target_latency
    
    @given(st.integers(min_value=1, max_value=5000))
    def test_config_valid_chunk_sizes(self, chunk_size):
        """Property test: valid chunk size values."""
        config = PipelineConfig(chunk_size_ms=chunk_size)
        assert config.chunk_size_ms == chunk_size


class TestPipelineResult:
    """Test pipeline result dataclass."""
    
    def test_pipeline_result_creation(self):
        """Test creating pipeline result with required fields."""
        result = PipelineResult(
            session_id="test_session",
            chunk_ids=[1, 2, 3],
            success=True,
            translated_audio=b"test_audio"
        )
        assert result.session_id == "test_session"
        assert result.chunk_ids == [1, 2, 3]
        assert result.success is True
        assert result.translated_audio == b"test_audio"
        assert result.stage_latencies == {}
        assert result.total_latency_ms == 0.0
    
    def test_pipeline_result_with_latencies(self):
        """Test pipeline result with stage latencies."""
        result = PipelineResult(
            session_id="test",
            chunk_ids=[1],
            stage_latencies={"asr": 500.0, "mt": 200.0, "tts": 300.0},
            total_latency_ms=1000.0
        )
        assert result.stage_latencies["asr"] == 500.0
        assert result.total_latency_ms == 1000.0


class TestCoordinatorStats:
    """Test coordinator statistics dataclass."""
    
    def test_empty_stats_creation(self):
        """Test creating empty coordinator stats."""
        stats = CoordinatorStats()
        assert stats.buffer_stats == {}
        assert stats.queue_stats == {}
        assert stats.sessions_processed == 0
        assert stats.target_compliance_rate == 1.0
    
    def test_populated_stats(self):
        """Test coordinator stats with data."""
        stats = CoordinatorStats(
            buffer_stats={"total_chunks": 5},
            queue_stats={"tasks_processed": 10},
            sessions_processed=10,
            avg_pipeline_latency_ms=1500.0,
            target_compliance_rate=0.95
        )
        assert stats.buffer_stats["total_chunks"] == 5
        assert stats.sessions_processed == 10
        assert stats.avg_pipeline_latency_ms == 1500.0


class TestStreamingPipelineCoordinator:
    """Test streaming pipeline coordinator class."""
    
    @pytest.fixture
    def mock_dependencies(self):
        """Mock external dependencies."""
        with patch('app.pipeline_coordinator.create_default_buffer') as mock_buffer_factory, \
             patch('app.pipeline_coordinator.create_optimized_queue') as mock_queue_factory, \
             patch('app.pipeline_coordinator.create_latency_monitor') as mock_monitor_factory:
            
            mock_buffer = Mock()
            mock_queue = Mock()
            mock_monitor = Mock()
            
            mock_buffer_factory.return_value = mock_buffer
            mock_queue_factory.return_value = mock_queue
            mock_monitor_factory.return_value = mock_monitor
            
            yield {
                'buffer': mock_buffer,
                'queue': mock_queue,
                'monitor': mock_monitor
            }
    
    def test_coordinator_initialization(self, mock_dependencies):
        """Test coordinator initialization with mocked dependencies."""
        coordinator = StreamingPipelineCoordinator("test_session")
        
        assert coordinator.session_id == "test_session"
        assert isinstance(coordinator.config, PipelineConfig)
        assert coordinator._active is False
        assert coordinator._session_counter == 0
    
    def test_coordinator_with_custom_config(self, mock_dependencies):
        """Test coordinator with custom configuration."""
        config = PipelineConfig(target_latency_ms=1500.0, chunk_size_ms=500)
        coordinator = StreamingPipelineCoordinator("test", config)
        
        assert coordinator.config.target_latency_ms == 1500.0
        assert coordinator.config.chunk_size_ms == 500
    
    @pytest.mark.asyncio
    async def test_start_pipeline_activation(self, mock_dependencies):
        """Test starting pipeline activates coordinator."""
        coordinator = StreamingPipelineCoordinator("test")
        mock_dependencies['queue'].start_workers = AsyncMock()
        
        async def mock_processor(task):
            return PipelineResult(session_id="test", chunk_ids=[])
        
        await coordinator.start_pipeline(mock_processor)
        
        assert coordinator._active is True
        assert coordinator._processor_func is mock_processor
        mock_dependencies['queue'].start_workers.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_start_pipeline_idempotent(self, mock_dependencies):
        """Test starting pipeline multiple times is idempotent."""
        coordinator = StreamingPipelineCoordinator("test")
        mock_dependencies['queue'].start_workers = AsyncMock()
        
        async def mock_processor(task):
            return PipelineResult(session_id="test", chunk_ids=[])
        
        await coordinator.start_pipeline(mock_processor)
        await coordinator.start_pipeline(mock_processor)  # Second call
        
        assert mock_dependencies['queue'].start_workers.call_count == 1
    
    @pytest.mark.asyncio
    async def test_stop_pipeline_deactivation(self, mock_dependencies):
        """Test stopping pipeline deactivates coordinator."""
        coordinator = StreamingPipelineCoordinator("test")
        mock_dependencies['queue'].start_workers = AsyncMock()
        mock_dependencies['queue'].stop_workers = AsyncMock()
        
        async def mock_processor(task):
            return PipelineResult(session_id="test", chunk_ids=[])
        
        await coordinator.start_pipeline(mock_processor)
        await coordinator.stop_pipeline()
        
        assert coordinator._active is False
        mock_dependencies['queue'].stop_workers.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_add_audio_chunk_inactive_coordinator(self, mock_dependencies):
        """Test adding audio chunk to inactive coordinator."""
        coordinator = StreamingPipelineCoordinator("test")
        
        result = await coordinator.add_audio_chunk(b"audio_data", 1000)
        
        assert result is False
        mock_dependencies['buffer'].add_chunk.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_add_audio_chunk_no_segment_ready(self, mock_dependencies):
        """Test adding audio chunk when no segment is ready."""
        coordinator = StreamingPipelineCoordinator("test")
        coordinator._active = True
        
        mock_dependencies['buffer'].get_processing_segment.return_value = None
        
        result = await coordinator.add_audio_chunk(b"audio_data", 1000, True)
        
        assert result is True
        mock_dependencies['buffer'].add_chunk.assert_called_once_with(b"audio_data", 1000, True)
        mock_dependencies['buffer'].get_processing_segment.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_add_audio_chunk_with_segment_processing(self, mock_dependencies):
        """Test adding audio chunk that triggers segment processing."""
        coordinator = StreamingPipelineCoordinator("test")
        coordinator._active = True
        
        mock_dependencies['buffer'].get_processing_segment.return_value = (b"combined_audio", [1, 2, 3])
        mock_dependencies['queue'].enqueue_task = AsyncMock(return_value=True)
        
        result = await coordinator.add_audio_chunk(b"audio_data", 1000)
        
        assert result is True
        mock_dependencies['queue'].enqueue_task.assert_called_once()
        mock_dependencies['buffer'].mark_chunks_processed.assert_called_once_with([1, 2, 3])
        assert coordinator._session_counter == 1
    
    @pytest.mark.asyncio
    async def test_add_audio_chunk_queue_full_backpressure(self, mock_dependencies):
        """Test backpressure handling when queue is full."""
        coordinator = StreamingPipelineCoordinator("test")
        coordinator._active = True
        
        mock_dependencies['buffer'].get_processing_segment.return_value = (b"audio", [1])
        mock_dependencies['queue'].enqueue_task = AsyncMock(return_value=False)
        
        result = await coordinator.add_audio_chunk(b"audio", 1000)
        
        assert result is False
        mock_dependencies['buffer'].mark_chunks_processed.assert_not_called()
        assert coordinator._session_counter == 0
    
    @pytest.mark.asyncio
    async def test_get_next_result_empty_queue(self, mock_dependencies):
        """Test getting result from empty queue."""
        coordinator = StreamingPipelineCoordinator("test")
        
        result = await coordinator.get_next_result()
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_get_next_result_with_data(self, mock_dependencies):
        """Test getting result when data is available."""
        coordinator = StreamingPipelineCoordinator("test")
        expected_result = PipelineResult(session_id="test", chunk_ids=[1])
        
        # Put result in queue manually
        await coordinator._results_queue.put(expected_result)
        
        result = await coordinator.get_next_result()
        
        assert result is expected_result
    
    def test_get_pipeline_stats_aggregation(self, mock_dependencies):
        """Test pipeline statistics aggregation."""
        coordinator = StreamingPipelineCoordinator("test")
        
        mock_dependencies['buffer'].get_buffer_stats.return_value = {"total_chunks": 5}
        mock_dependencies['queue'].get_queue_stats.return_value = {"tasks_processed": 10}
        mock_dependencies['monitor'].get_stage_statistics.return_value = {"avg_ms": 500.0}
        mock_dependencies['monitor'].get_target_compliance_rate.return_value = 0.95
        
        stats = coordinator.get_pipeline_stats()
        
        assert isinstance(stats, CoordinatorStats)
        assert stats.buffer_stats["total_chunks"] == 5
        assert stats.queue_stats["tasks_processed"] == 10
        assert stats.target_compliance_rate == 0.95
    
    def test_is_healthy_inactive_coordinator(self, mock_dependencies):
        """Test health check on inactive coordinator."""
        coordinator = StreamingPipelineCoordinator("test")
        
        assert coordinator.is_healthy() is False
    
    def test_is_healthy_queue_full(self, mock_dependencies):
        """Test health check when queue is full."""
        coordinator = StreamingPipelineCoordinator("test")
        coordinator._active = True
        
        mock_dependencies['queue'].is_queue_full.return_value = True
        
        assert coordinator.is_healthy() is False
    
    def test_is_healthy_low_compliance(self, mock_dependencies):
        """Test health check with low latency compliance."""
        coordinator = StreamingPipelineCoordinator("test")
        coordinator._active = True
        
        mock_dependencies['queue'].is_queue_full.return_value = False
        mock_dependencies['monitor'].get_target_compliance_rate.return_value = 0.7  # Below 80%
        
        assert coordinator.is_healthy() is False
    
    def test_is_healthy_good_conditions(self, mock_dependencies):
        """Test health check under good conditions."""
        coordinator = StreamingPipelineCoordinator("test")
        coordinator._active = True
        
        mock_dependencies['queue'].is_queue_full.return_value = False
        mock_dependencies['monitor'].get_target_compliance_rate.return_value = 0.9
        
        assert coordinator.is_healthy() is True
    
    @pytest.mark.asyncio
    async def test_handle_backpressure_clears_buffer(self, mock_dependencies):
        """Test backpressure handling clears buffer."""
        coordinator = StreamingPipelineCoordinator("test")
        
        mock_dependencies['queue'].is_queue_full.return_value = True
        
        await coordinator.handle_backpressure()
        
        mock_dependencies['buffer'].clear.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_handle_backpressure_no_action_when_queue_not_full(self, mock_dependencies):
        """Test backpressure handling when queue is not full."""
        coordinator = StreamingPipelineCoordinator("test")
        
        mock_dependencies['queue'].is_queue_full.return_value = False
        
        await coordinator.handle_backpressure()
        
        mock_dependencies['buffer'].clear.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_pipeline_task_processor_no_processor_func(self, mock_dependencies):
        """Test pipeline task processor with no processor function set."""
        coordinator = StreamingPipelineCoordinator("test")
        
        # Don't set processor function
        task = ProcessingTask(
            task_id="test_task",
            audio_data=b"test",
            session_id="test",
            timestamp=1.0,
            metadata={"chunk_ids": [1]}
        )
        
        # Should return early without processing
        await coordinator._pipeline_task_processor(task)
        
        # No result should be added to queue
        result = await coordinator.get_next_result()
        assert result is None
    
    @pytest.mark.asyncio
    async def test_pipeline_task_processor_success(self, mock_dependencies):
        """Test successful pipeline task processing."""
        coordinator = StreamingPipelineCoordinator("test")
        
        # Setup monitor mocks with context manager support
        mock_dependencies['monitor'].start_session = Mock()
        mock_dependencies['monitor'].end_session = Mock(return_value={
            "asr": Mock(duration_ms=500.0),
            "mt": Mock(duration_ms=200.0),
            "tts": Mock(duration_ms=300.0)
        })
        
        # Mock track_stage as a context manager
        mock_context = Mock()
        mock_context.__enter__ = Mock(return_value=mock_context)
        mock_context.__exit__ = Mock(return_value=None)
        mock_dependencies['monitor'].track_stage = Mock(return_value=mock_context)
        
        # Setup processor function
        async def mock_processor(task):
            return PipelineResult(
                session_id=task.session_id,
                chunk_ids=[1, 2, 3],
                success=True,
                translated_audio=b"test_output"
            )
        
        coordinator._processor_func = mock_processor
        
        task = ProcessingTask(
            task_id="test_task",
            audio_data=b"test",
            session_id="test",
            timestamp=1.0,
            metadata={"chunk_ids": [1]}
        )
        
        await coordinator._pipeline_task_processor(task)
        
        # Should have successful result in queue
        result = await coordinator.get_next_result()
        assert result is not None
        assert result.success is True
        assert result.translated_audio == b"test_output"


class TestFactoryFunctions:
    """Test factory functions."""
    
    @patch('app.pipeline_coordinator.StreamingPipelineCoordinator')
    def test_create_pipeline_coordinator(self, mock_coordinator_class):
        """Test factory function creates coordinator."""
        mock_instance = Mock()
        mock_coordinator_class.return_value = mock_instance
        
        result = create_pipeline_coordinator("test_session")
        
        mock_coordinator_class.assert_called_once_with("test_session", None)
        assert result is mock_instance
    
    @patch('app.pipeline_coordinator.StreamingPipelineCoordinator')
    def test_create_pipeline_coordinator_with_config(self, mock_coordinator_class):
        """Test factory function with custom config."""
        mock_instance = Mock()
        mock_coordinator_class.return_value = mock_instance
        config = PipelineConfig(target_latency_ms=1500.0)
        
        result = create_pipeline_coordinator("test", config)
        
        mock_coordinator_class.assert_called_once_with("test", config)
    
    def test_create_realtime_config(self):
        """Test creating real-time optimized configuration."""
        config = create_realtime_config()
        
        assert isinstance(config, PipelineConfig)
        assert config.target_latency_ms == 1800.0
        assert config.chunk_size_ms == 600
        assert config.max_buffer_duration_ms == 3000
        assert config.enable_parallelization is True


class TestPropertyBasedTesting:
    """Property-based tests using Hypothesis."""
    
    @given(
        st.text(min_size=1, max_size=50),
        st.lists(st.integers(min_value=1, max_value=1000), min_size=1, max_size=10),
        st.booleans(),
        st.floats(min_value=0.0, max_value=5000.0)
    )
    def test_pipeline_result_properties(self, session_id, chunk_ids, success, latency):
        """Property test: PipelineResult maintains data integrity."""
        result = PipelineResult(
            session_id=session_id,
            chunk_ids=chunk_ids,
            success=success,
            total_latency_ms=latency
        )
        
        assert result.session_id == session_id
        assert result.chunk_ids == chunk_ids
        assert result.success == success
        assert result.total_latency_ms == latency
    
    @given(
        st.integers(min_value=1000, max_value=10000),
        st.integers(min_value=100, max_value=2000),
        st.floats(min_value=500.0, max_value=5000.0)
    )
    def test_pipeline_config_properties(self, buffer_duration, chunk_size, target_latency):
        """Property test: PipelineConfig accepts valid ranges."""
        config = PipelineConfig(
            max_buffer_duration_ms=buffer_duration,
            chunk_size_ms=chunk_size,
            target_latency_ms=target_latency
        )
        
        assert config.max_buffer_duration_ms == buffer_duration
        assert config.chunk_size_ms == chunk_size
        assert config.target_latency_ms == target_latency
    
    @given(
        st.dictionaries(
            st.text(min_size=1, max_size=20),
            st.integers(min_value=0, max_value=100),
            min_size=0,
            max_size=10
        ),
        st.integers(min_value=0, max_value=1000),
        st.floats(min_value=0.0, max_value=1.0)
    )
    def test_coordinator_stats_properties(self, buffer_stats, sessions, compliance_rate):
        """Property test: CoordinatorStats handles various data."""
        stats = CoordinatorStats(
            buffer_stats=buffer_stats,
            sessions_processed=sessions,
            target_compliance_rate=compliance_rate
        )
        
        assert stats.buffer_stats == buffer_stats
        assert stats.sessions_processed == sessions
        assert stats.target_compliance_rate == compliance_rate
    
    @patch('app.pipeline_coordinator.create_default_buffer')
    @patch('app.pipeline_coordinator.create_optimized_queue')
    @patch('app.pipeline_coordinator.create_latency_monitor')
    @given(
        st.text(min_size=1, max_size=100)
    )
    def test_coordinator_initialization_properties(self, mock_monitor, mock_queue, mock_buffer, session_id):
        """Property test: Coordinator initializes with various session IDs."""
        mock_buffer.return_value = Mock()
        mock_queue.return_value = Mock()
        mock_monitor.return_value = Mock()
        
        coordinator = StreamingPipelineCoordinator(session_id)
        
        assert coordinator.session_id == session_id
        assert coordinator._active is False
        assert coordinator._session_counter == 0


@pytest.mark.asyncio
class TestAsyncIntegration:
    """Integration tests for async functionality."""
    
    @patch('app.pipeline_coordinator.create_default_buffer')
    @patch('app.pipeline_coordinator.create_optimized_queue')
    @patch('app.pipeline_coordinator.create_latency_monitor')
    async def test_full_pipeline_lifecycle(self, mock_monitor_factory, mock_queue_factory, mock_buffer_factory):
        """Test complete pipeline lifecycle."""
        # Setup mocks
        mock_buffer = Mock()
        mock_queue = Mock()
        mock_monitor = Mock()
        
        mock_buffer_factory.return_value = mock_buffer
        mock_queue_factory.return_value = mock_queue
        mock_monitor_factory.return_value = mock_monitor
        
        mock_queue.start_workers = AsyncMock()
        mock_queue.stop_workers = AsyncMock()
        mock_queue.enqueue_task = AsyncMock(return_value=True)
        
        # Create coordinator
        coordinator = StreamingPipelineCoordinator("integration_test")
        
        # Mock processor function
        async def mock_processor(task):
            return PipelineResult(
                session_id=task.session_id,
                chunk_ids=[1, 2, 3],
                success=True,
                translated_audio=b"test_output"
            )
        
        # Test lifecycle
        await coordinator.start_pipeline(mock_processor)
        assert coordinator._active is True
        
        # Configure buffer to return a segment
        mock_buffer.get_processing_segment.return_value = (b"test_audio", [1, 2, 3])
        
        # Add audio chunk
        result = await coordinator.add_audio_chunk(b"test_audio", 1000, True)
        assert result is True
        
        # Stop pipeline
        await coordinator.stop_pipeline()
        assert coordinator._active is False
    
    @patch('app.pipeline_coordinator.create_default_buffer')
    @patch('app.pipeline_coordinator.create_optimized_queue')
    @patch('app.pipeline_coordinator.create_latency_monitor')
    async def test_error_handling_in_pipeline(self, mock_monitor_factory, mock_queue_factory, mock_buffer_factory):
        """Test error handling in pipeline processing."""
        # Setup mocks
        mock_buffer = Mock()
        mock_queue = Mock()
        mock_monitor = Mock()
        
        mock_buffer_factory.return_value = mock_buffer
        mock_queue_factory.return_value = mock_queue
        mock_monitor_factory.return_value = mock_monitor
        
        mock_monitor.start_session = Mock()
        mock_monitor.end_session = Mock(return_value={})
        
        # Mock track_stage as a context manager for error case
        mock_context = Mock()
        mock_context.__enter__ = Mock(return_value=mock_context)
        mock_context.__exit__ = Mock(return_value=None)
        mock_monitor.track_stage = Mock(return_value=mock_context)
        
        coordinator = StreamingPipelineCoordinator("error_test")
        
        # Mock processor that raises exception
        async def failing_processor(task):
            raise ValueError("Test error")
        
        # Set the processor function so the method doesn't return early
        coordinator._processor_func = failing_processor
        
        # Test error handling - use positive timestamp
        await coordinator._pipeline_task_processor(
            ProcessingTask(
                task_id="test_task",
                audio_data=b"test",
                session_id="error_test",
                timestamp=1.0,
                metadata={"chunk_ids": [1]}
            )
        )
        
        # Should have error result in queue
        error_result = await coordinator.get_next_result()
        assert error_result is not None
        assert error_result.success is False
        assert "Test error" in error_result.error_message
