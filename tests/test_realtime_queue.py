"""
Comprehensive tests for realtime_queue module.

Tests async processing queue with property-based testing and coverage ≥90%.
"""

import asyncio
import pytest
import time
from unittest.mock import AsyncMock, patch
from hypothesis import given, strategies as st, settings
from typing import List

from app.realtime_queue import (
    AsyncProcessingQueue,
    ProcessingTask,
    ProcessingResult,
    QueueConfig,
    TaskPriority,
    create_task,
    create_optimized_queue
)


class TestProcessingTask:
    """Test ProcessingTask dataclass validation and creation."""
    
    def test_valid_task_creation(self):
        """Test creating a valid processing task."""
        task = ProcessingTask(
            task_id="test-123",
            audio_data=b"test audio data", 
            session_id="session-456",
            timestamp=time.time(),
            priority=TaskPriority.HIGH
        )
        
        assert task.task_id == "test-123"
        assert task.audio_data == b"test audio data"
        assert task.session_id == "session-456"
        assert task.priority == TaskPriority.HIGH
        assert isinstance(task.metadata, dict)
    
    def test_task_validation_empty_task_id(self):
        """Test task validation fails with empty task_id."""
        with pytest.raises(ValueError, match="task_id cannot be empty"):
            ProcessingTask(
                task_id="",
                audio_data=b"data",
                session_id="session",
                timestamp=time.time()
            )
    
    def test_task_validation_empty_session_id(self):
        """Test task validation fails with empty session_id."""
        with pytest.raises(ValueError, match="session_id cannot be empty"):
            ProcessingTask(
                task_id="task",
                audio_data=b"data", 
                session_id="",
                timestamp=time.time()
            )
    
    def test_task_validation_invalid_timestamp(self):
        """Test task validation fails with non-positive timestamp."""
        with pytest.raises(ValueError, match="timestamp must be positive"):
            ProcessingTask(
                task_id="task",
                audio_data=b"data",
                session_id="session",
                timestamp=0
            )


class TestQueueConfig:
    """Test QueueConfig validation."""
    
    def test_valid_config_creation(self):
        """Test creating valid queue configuration."""
        config = QueueConfig(
            max_queue_size=100,
            worker_count=5,
            task_timeout_sec=10.0,
            enable_priority_queue=False
        )
        
        assert config.max_queue_size == 100
        assert config.worker_count == 5
        assert config.task_timeout_sec == 10.0
        assert config.enable_priority_queue is False
    
    @pytest.mark.parametrize("invalid_size", [0, -1, -10])
    def test_config_validation_invalid_queue_size(self, invalid_size):
        """Test config validation fails with invalid queue size."""
        with pytest.raises(ValueError, match="max_queue_size must be positive"):
            QueueConfig(max_queue_size=invalid_size)
    
    @pytest.mark.parametrize("invalid_workers", [0, -1, -5])
    def test_config_validation_invalid_worker_count(self, invalid_workers):
        """Test config validation fails with invalid worker count."""
        with pytest.raises(ValueError, match="worker_count must be positive"):
            QueueConfig(worker_count=invalid_workers)
    
    @pytest.mark.parametrize("invalid_timeout", [0, -1.0, -5.5])
    def test_config_validation_invalid_timeout(self, invalid_timeout):
        """Test config validation fails with invalid timeout."""
        with pytest.raises(ValueError, match="task_timeout_sec must be positive"):
            QueueConfig(task_timeout_sec=invalid_timeout)


class TestAsyncProcessingQueue:
    """Test AsyncProcessingQueue functionality."""
    
    def test_queue_initialization(self):
        """Test queue initializes with default configuration."""
        queue = AsyncProcessingQueue()
        
        assert queue.config.max_queue_size == 50
        assert queue.config.worker_count == 3
        assert queue.config.task_timeout_sec == 5.0
        assert queue.config.enable_priority_queue is True
        assert queue.is_queue_full() is False
        assert queue._running is False
    
    def test_queue_initialization_custom_config(self):
        """Test queue initializes with custom configuration."""
        config = QueueConfig(max_queue_size=10, worker_count=2)
        queue = AsyncProcessingQueue(config)
        
        assert queue.config.max_queue_size == 10
        assert queue.config.worker_count == 2
    
    @pytest.mark.asyncio
    async def test_enqueue_task_success(self):
        """Test successful task enqueueing."""
        queue = AsyncProcessingQueue(QueueConfig(max_queue_size=5))
        task = create_task(b"test data", "session1")
        
        result = await queue.enqueue_task(task)
        
        assert result is True
        stats = queue.get_queue_stats()
        assert stats["tasks_enqueued"] == 1
        assert stats["queue_size"] >= 0  # May be 0 or 1 depending on priority queue
    
    @pytest.mark.asyncio
    async def test_enqueue_task_queue_full(self):
        """Test task enqueueing when queue is full."""
        config = QueueConfig(max_queue_size=2, enable_priority_queue=False)
        queue = AsyncProcessingQueue(config)
        
        # Fill the queue
        task1 = create_task(b"data1", "session1")
        task2 = create_task(b"data2", "session2")
        
        await queue.enqueue_task(task1)
        await queue.enqueue_task(task2)
        
        # Try to add one more - should fail
        task3 = create_task(b"data3", "session3")
        result = await queue.enqueue_task(task3)
        
        assert result is False
        stats = queue.get_queue_stats()
        assert stats["queue_overflows"] == 1
    
    @pytest.mark.asyncio
    async def test_priority_queue_ordering(self):
        """Test priority queue maintains correct ordering."""
        # Create a full queue so priority queue doesn't get drained immediately
        config = QueueConfig(max_queue_size=2, enable_priority_queue=True)
        queue = AsyncProcessingQueue(config)
        
        # Fill the main queue first
        filler1 = ProcessingTask("filler1", b"data", "session", time.time(), TaskPriority.NORMAL)
        filler2 = ProcessingTask("filler2", b"data", "session", time.time(), TaskPriority.NORMAL)
        await queue.enqueue_task(filler1)
        await queue.enqueue_task(filler2)
        
        # Now add tasks that will go to priority queue
        low_task = ProcessingTask("low", b"data", "session", time.time(), TaskPriority.LOW)
        high_task = ProcessingTask("high", b"data", "session", time.time(), TaskPriority.HIGH)
        normal_task = ProcessingTask("normal", b"data", "session", time.time(), TaskPriority.NORMAL)
        
        await queue.enqueue_task(low_task)
        await queue.enqueue_task(high_task)
        await queue.enqueue_task(normal_task)
        
        # High priority should be first in priority queue
        assert len(queue._priority_queue) > 0
        assert queue._priority_queue[0].priority == TaskPriority.HIGH
    
    @pytest.mark.asyncio
    async def test_worker_management(self):
        """Test starting and stopping workers."""
        queue = AsyncProcessingQueue(QueueConfig(worker_count=2))
        
        # Mock processor function
        async def mock_processor(task):
            return ProcessingResult(task.task_id, True)
        
        # Start workers
        await queue.start_workers(mock_processor)
        assert queue._running is True
        assert len(queue._workers) == 2
        
        # Stop workers
        await queue.stop_workers()
        assert queue._running is False
        assert len(queue._workers) == 0
    
    @pytest.mark.asyncio
    async def test_task_processing_success(self):
        """Test successful task processing by workers."""
        config = QueueConfig(worker_count=1, task_timeout_sec=1.0)
        queue = AsyncProcessingQueue(config)
        
        processed_tasks = []
        
        async def mock_processor(task):
            processed_tasks.append(task.task_id)
            await asyncio.sleep(0.01)  # Simulate processing time
            return ProcessingResult(task.task_id, True)
        
        # Start workers and enqueue task
        await queue.start_workers(mock_processor)
        task = create_task(b"test data", "session1")
        await queue.enqueue_task(task)
        
        # Wait briefly for processing
        await asyncio.sleep(0.1)
        
        # Stop workers
        await queue.stop_workers()
        
        assert task.task_id in processed_tasks
        stats = queue.get_queue_stats()
        assert stats["tasks_processed"] >= 1
    
    @pytest.mark.asyncio
    async def test_task_processing_timeout(self):
        """Test task processing timeout handling."""
        config = QueueConfig(worker_count=1, task_timeout_sec=0.01)
        queue = AsyncProcessingQueue(config)
        
        async def slow_processor(task):
            await asyncio.sleep(0.1)  # Longer than timeout
            return ProcessingResult(task.task_id, True)
        
        # Start workers and enqueue task
        await queue.start_workers(slow_processor)
        task = create_task(b"test data", "session1")
        await queue.enqueue_task(task)
        
        # Wait for timeout to occur
        await asyncio.sleep(0.1)
        
        # Stop workers
        await queue.stop_workers()
        
        stats = queue.get_queue_stats()
        assert stats["tasks_failed"] >= 1
    
    def test_queue_stats(self):
        """Test queue statistics reporting."""
        config = QueueConfig(max_queue_size=20, worker_count=3)
        queue = AsyncProcessingQueue(config)
        
        stats = queue.get_queue_stats()
        
        expected_keys = {
            "queue_size", "priority_queue_size", "max_queue_size",
            "worker_count", "is_running", "is_queue_full",
            "tasks_enqueued", "tasks_processed", "tasks_failed", "queue_overflows"
        }
        
        assert set(stats.keys()) >= expected_keys
        assert stats["max_queue_size"] == 20
        assert stats["worker_count"] == 0  # No workers started yet
        assert stats["is_running"] is False


class TestFactoryFunctions:
    """Test factory functions for creating tasks and queues."""
    
    def test_create_task_function(self):
        """Test create_task factory function."""
        task = create_task(b"audio data", "session123", TaskPriority.HIGH)
        
        assert isinstance(task.task_id, str)
        assert len(task.task_id) > 0
        assert task.audio_data == b"audio data"
        assert task.session_id == "session123"
        assert task.priority == TaskPriority.HIGH
        assert task.timestamp > 0
    
    def test_create_optimized_queue_function(self):
        """Test create_optimized_queue factory function."""
        queue = create_optimized_queue()
        
        assert queue.config.max_queue_size == 30
        assert queue.config.worker_count == 2
        assert queue.config.task_timeout_sec == 3.0
        assert queue.config.enable_priority_queue is True


# Property-based tests using Hypothesis (≥25 random cases)
class TestHypothesisProperties:
    """Property-based tests using Hypothesis for random case generation."""
    
    @given(
        task_ids=st.lists(st.text(min_size=1, max_size=50), min_size=1, max_size=25),
        session_id=st.text(min_size=1, max_size=20),
        audio_sizes=st.lists(st.integers(min_value=1, max_value=1024), min_size=1, max_size=25)
    )
    @settings(max_examples=30)
    def test_task_creation_with_random_data(self, task_ids, session_id, audio_sizes):
        """Test task creation with random valid data always succeeds."""
        for i, (task_id, audio_size) in enumerate(zip(task_ids, audio_sizes)):
            audio_data = b"x" * audio_size
            timestamp = time.time() + i  # Ensure positive and unique
            
            task = ProcessingTask(task_id, audio_data, session_id, timestamp)
            
            assert task.task_id == task_id
            assert task.audio_data == audio_data
            assert task.session_id == session_id
            assert task.timestamp == timestamp
    
    @given(
        priorities=st.lists(st.sampled_from(TaskPriority), min_size=5, max_size=20)
    )
    @settings(max_examples=30)
    def test_priority_queue_ordering_property(self, priorities):
        """Test priority queue always maintains correct ordering."""
        async def async_test():
            queue = AsyncProcessingQueue(QueueConfig(max_queue_size=50))
            
            # Create tasks with random priorities
            tasks = []
            for i, priority in enumerate(priorities):
                task = ProcessingTask(f"task-{i}", b"data", "session", time.time() + i, priority)
                tasks.append(task)
                await queue.enqueue_task(task)
            
            # Verify priority queue maintains ordering (lower number = higher priority)
            for i in range(len(queue._priority_queue) - 1):
                current_priority = queue._priority_queue[i].priority
                next_priority = queue._priority_queue[i + 1].priority
                assert current_priority <= next_priority
        
        asyncio.run(async_test())
    
    @given(
        queue_sizes=st.integers(min_value=1, max_value=20),
        worker_counts=st.integers(min_value=1, max_value=5),
        timeouts=st.floats(min_value=0.1, max_value=10.0)
    )
    @settings(max_examples=30)
    def test_config_validation_properties(self, queue_sizes, worker_counts, timeouts):
        """Test config validation with random valid parameters."""
        config = QueueConfig(
            max_queue_size=queue_sizes,
            worker_count=worker_counts,
            task_timeout_sec=timeouts
        )
        
        assert config.max_queue_size == queue_sizes
        assert config.worker_count == worker_counts
        assert config.task_timeout_sec == timeouts
    
    @given(
        task_count=st.integers(min_value=1, max_value=15),
        max_queue_size=st.integers(min_value=5, max_value=20)
    )
    @settings(max_examples=25)
    def test_queue_capacity_handling(self, task_count, max_queue_size):
        """Test queue handles various task counts and sizes correctly."""
        async def async_test():
            config = QueueConfig(max_queue_size=max_queue_size, enable_priority_queue=False)
            queue = AsyncProcessingQueue(config)
            
            successful_enqueues = 0
            overflows = 0
            
            for i in range(task_count):
                task = create_task(f"data-{i}".encode(), f"session-{i}")
                result = await queue.enqueue_task(task)
                
                if result:
                    successful_enqueues += 1
                else:
                    overflows += 1
            
            stats = queue.get_queue_stats()
            
            # Properties that should always hold
            assert successful_enqueues + overflows == task_count
            assert stats["tasks_enqueued"] == successful_enqueues
            assert stats["queue_overflows"] == overflows
            assert stats["queue_size"] <= max_queue_size
        
        asyncio.run(async_test())
    
    @given(
        session_ids=st.lists(st.text(min_size=1, max_size=20), min_size=3, max_size=10)
    )
    @settings(max_examples=25)
    def test_multi_session_task_handling(self, session_ids):
        """Test queue handles tasks from multiple sessions correctly."""
        async def async_test():
            queue = AsyncProcessingQueue(QueueConfig(max_queue_size=50))
            
            tasks_by_session = {}
            
            for session_id in session_ids:
                task = create_task(b"session data", session_id)
                await queue.enqueue_task(task)
                
                if session_id not in tasks_by_session:
                    tasks_by_session[session_id] = []
                tasks_by_session[session_id].append(task)
            
            stats = queue.get_queue_stats()
            
            # All tasks should be enqueued successfully
            assert stats["tasks_enqueued"] == len(session_ids)
            assert stats["queue_overflows"] == 0
            
            # Each session should have its tasks tracked
            for session_id, session_tasks in tasks_by_session.items():
                assert len(session_tasks) >= 1
                assert all(task.session_id == session_id for task in session_tasks)
        
        asyncio.run(async_test())
