"""
Real-time Processing Queue System for Speech Translation Pipeline.

Provides non-blocking async task queue with backpressure control and priority handling.
No external I/O - pure async queue operations for memory-safe real-time processing.
"""

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional, Dict, Any, Callable, Awaitable
import uuid


class TaskPriority(IntEnum):
    """Task priority levels (lower number = higher priority)."""
    HIGH = 1
    NORMAL = 2
    LOW = 3


@dataclass
class ProcessingTask:
    """Task item for the processing queue."""
    task_id: str
    audio_data: bytes
    session_id: str
    timestamp: float
    priority: TaskPriority = TaskPriority.NORMAL
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate task data."""
        if not self.task_id:
            raise ValueError("task_id cannot be empty")
        if not self.session_id:
            raise ValueError("session_id cannot be empty")
        if self.timestamp <= 0:
            raise ValueError("timestamp must be positive")


@dataclass
class ProcessingResult:
    """Result from processing a task."""
    task_id: str
    success: bool
    result_data: Optional[bytes] = None
    error_message: Optional[str] = None
    processing_time_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class QueueConfig:
    """Configuration for processing queue behavior."""
    max_queue_size: int = 50
    worker_count: int = 3
    task_timeout_sec: float = 5.0
    enable_priority_queue: bool = True
    
    def __post_init__(self):
        """Validate configuration."""
        if self.max_queue_size <= 0:
            raise ValueError("max_queue_size must be positive")
        if self.worker_count <= 0:
            raise ValueError("worker_count must be positive")
        if self.task_timeout_sec <= 0:
            raise ValueError("task_timeout_sec must be positive")


class AsyncProcessingQueue:
    """
    Async processing queue manager with backpressure control.
    
    Provides non-blocking task queuing with configurable workers and priority handling.
    Designed for real-time audio processing with sub-2 second latency requirements.
    """
    
    def __init__(self, config: Optional[QueueConfig] = None):
        """Initialize processing queue with configuration."""
        self.config = config or QueueConfig()
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=self.config.max_queue_size)
        self._priority_queue: deque = deque()
        self._workers: list = []
        self._running = False
        self._stats = {
            "tasks_enqueued": 0,
            "tasks_processed": 0,
            "tasks_failed": 0,
            "queue_overflows": 0
        }
        
        logging.info(f"Initialized AsyncProcessingQueue with {self.config}")
    
    async def enqueue_task(self, task: ProcessingTask) -> bool:
        """
        Add task to processing queue.
        
        Args:
            task: ProcessingTask to add to queue
            
        Returns:
            True if task was queued, False if queue is full (backpressure)
        """
        try:
            if self.config.enable_priority_queue:
                self._enqueue_with_priority(task)
            else:
                self._queue.put_nowait(task)
            
            self._stats["tasks_enqueued"] += 1
            logging.debug(f"Enqueued task {task.task_id} for session {task.session_id}")
            return True
            
        except asyncio.QueueFull:
            self._stats["queue_overflows"] += 1
            logging.warning(f"Queue full, dropped task {task.task_id}")
            return False
    
    def _enqueue_with_priority(self, task: ProcessingTask) -> None:
        """Add task to priority queue maintaining order."""
        # Insert task maintaining priority order (lower priority number = higher priority)
        inserted = False
        for i, existing_task in enumerate(self._priority_queue):
            if task.priority < existing_task.priority:
                self._priority_queue.insert(i, task)
                inserted = True
                break
        
        if not inserted:
            self._priority_queue.append(task)
        
        # Move from priority queue to async queue if space available
        if not self._queue.full() and self._priority_queue:
            next_task = self._priority_queue.popleft()
            self._queue.put_nowait(next_task)
    
    async def start_workers(self, processor_func: Callable[[ProcessingTask], Awaitable[ProcessingResult]]) -> None:
        """
        Start worker tasks for processing queue.
        
        Args:
            processor_func: Async function that processes tasks
        """
        if self._running:
            return
        
        self._running = True
        self._workers = []
        
        for worker_id in range(self.config.worker_count):
            worker = asyncio.create_task(
                self._worker_process_tasks(worker_id, processor_func)
            )
            self._workers.append(worker)
        
        logging.info(f"Started {len(self._workers)} worker tasks")
    
    async def stop_workers(self) -> None:
        """Stop all worker tasks gracefully."""
        if not self._running:
            return
        
        self._running = False
        
        # Cancel all worker tasks
        for worker in self._workers:
            worker.cancel()
        
        # Wait for workers to finish
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
        
        self._workers.clear()
        logging.info("Stopped all worker tasks")
    
    async def _worker_process_tasks(
        self, 
        worker_id: int, 
        processor_func: Callable[[ProcessingTask], Awaitable[ProcessingResult]]
    ) -> None:
        """Worker loop for processing tasks from queue."""
        logging.info(f"Worker {worker_id} started")
        
        while self._running:
            try:
                # Get task with timeout
                task = await asyncio.wait_for(
                    self._queue.get(), 
                    timeout=1.0  # Check running status every second
                )
                
                # Process task with timeout
                start_time = time.time()
                try:
                    result = await asyncio.wait_for(
                        processor_func(task),
                        timeout=self.config.task_timeout_sec
                    )
                    self._stats["tasks_processed"] += 1
                    
                except asyncio.TimeoutError:
                    self._stats["tasks_failed"] += 1
                    logging.warning(f"Worker {worker_id}: Task {task.task_id} timed out")
                    
                except Exception as e:
                    self._stats["tasks_failed"] += 1
                    logging.error(f"Worker {worker_id}: Task {task.task_id} failed: {e}")
                
                finally:
                    processing_time = (time.time() - start_time) * 1000
                    logging.debug(f"Worker {worker_id}: Processed task {task.task_id} "
                                f"in {processing_time:.1f}ms")
                
                # Mark task as done
                self._queue.task_done()
                
            except asyncio.TimeoutError:
                # Timeout on queue get - continue loop to check running status
                continue
            except asyncio.CancelledError:
                # Worker was cancelled
                break
            except Exception as e:
                logging.error(f"Worker {worker_id} unexpected error: {e}")
        
        logging.info(f"Worker {worker_id} stopped")
    
    def is_queue_full(self) -> bool:
        """Check if queue is at capacity (backpressure indicator)."""
        return self._queue.full()
    
    def get_queue_stats(self) -> Dict[str, Any]:
        """Get current queue statistics for monitoring."""
        return {
            "queue_size": self._queue.qsize(),
            "priority_queue_size": len(self._priority_queue),
            "max_queue_size": self.config.max_queue_size,
            "worker_count": len(self._workers),
            "is_running": self._running,
            "is_queue_full": self.is_queue_full(),
            **self._stats
        }
    
    async def wait_for_completion(self) -> None:
        """Wait for all currently queued tasks to complete."""
        await self._queue.join()


def create_task(audio_data: bytes, session_id: str, priority: TaskPriority = TaskPriority.NORMAL) -> ProcessingTask:
    """Factory function to create a processing task with generated ID."""
    return ProcessingTask(
        task_id=str(uuid.uuid4()),
        audio_data=audio_data,
        session_id=session_id,
        timestamp=time.time(),
        priority=priority
    )


def create_optimized_queue() -> AsyncProcessingQueue:
    """Create processing queue with optimized settings for real-time translation."""
    config = QueueConfig(
        max_queue_size=30,  # Smaller queue for low latency
        worker_count=2,     # Balanced for typical CPU cores
        task_timeout_sec=3.0,  # Strict timeout for real-time requirements
        enable_priority_queue=True
    )
    return AsyncProcessingQueue(config)
