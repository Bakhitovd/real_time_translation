"""
Streaming Pipeline Coordinator for Real-time Speech Translation.

Orchestrates StreamingAudioBuffer, AsyncProcessingQueue, and LatencyMonitor
to enable concurrent pipeline processing with sub-2 second latency.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, Callable, Awaitable, List
from enum import Enum

from app.streaming_buffer import StreamingAudioBuffer, AudioChunk, create_default_buffer, BufferConfig
from app.realtime_queue import AsyncProcessingQueue, ProcessingTask, TaskPriority, QueueConfig
from app.latency_monitor import LatencyMonitor, create_latency_monitor


class PipelineStage(Enum):
    """Pipeline processing stages."""
    ASR = "asr"
    MT = "mt"
    TTS = "tts"


@dataclass
class PipelineConfig:
    """Configuration for streaming pipeline coordinator."""
    max_buffer_duration_ms: int = 4000
    chunk_size_ms: int = 800
    overlap_ms: int = 150
    target_latency_ms: float = 2000.0
    queue_size: int = 30
    worker_count: int = 2
    enable_parallelization: bool = True
    
    def __post_init__(self):
        if self.target_latency_ms <= 0:
            raise ValueError("target_latency_ms must be positive")
        if self.chunk_size_ms <= 0:
            raise ValueError("chunk_size_ms must be positive")


@dataclass
class PipelineResult:
    """Result from pipeline processing with metadata."""
    session_id: str
    chunk_ids: List[int]
    translated_audio: Optional[bytes] = None
    success: bool = False
    stage_latencies: Dict[str, float] = field(default_factory=dict)
    total_latency_ms: float = 0.0
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CoordinatorStats:
    """Aggregated statistics from all pipeline components."""
    buffer_stats: Dict[str, Any] = field(default_factory=dict)
    queue_stats: Dict[str, Any] = field(default_factory=dict)
    latency_stats: Dict[str, Any] = field(default_factory=dict)
    sessions_processed: int = 0
    avg_pipeline_latency_ms: float = 0.0
    target_compliance_rate: float = 1.0


class StreamingPipelineCoordinator:
    """
    Coordinates streaming audio processing through ASR->MT->TTS pipeline.
    
    Enables concurrent processing: while ASR processes chunk N, MT processes 
    chunk N-1, and TTS processes chunk N-2 for sub-2 second latency.
    """
    
    def __init__(self, session_id: str, config: Optional[PipelineConfig] = None):
        """Initialize pipeline coordinator for a session."""
        self.session_id = session_id
        self.config = config or PipelineConfig()
        
        # Initialize components
        # Create buffer using pipeline config values when possible
        try:
            buffer_cfg = BufferConfig(
                max_chunk_size_ms=self.config.chunk_size_ms,
                overlap_ms=self.config.overlap_ms,
                max_silence_gap_ms=max(self.config.overlap_ms * 2, 400),
                max_buffer_duration_ms=self.config.max_buffer_duration_ms
            )
            self.buffer = StreamingAudioBuffer(buffer_cfg)
        except Exception:
            # Fall back to default buffer if BufferConfig creation fails
            self.buffer = create_default_buffer()

        # Create processing queue using pipeline config
        queue_cfg = QueueConfig(
            max_queue_size=self.config.queue_size,
            worker_count=self.config.worker_count,
            task_timeout_sec=10.0,
            enable_priority_queue=True
        )
        self.queue = AsyncProcessingQueue(queue_cfg)

        self.monitor = create_latency_monitor(
            target_ms=self.config.target_latency_ms,
            history_size=1000
        )
        
        # Pipeline state
        self._active = False
        self._processor_func: Optional[Callable] = None
        self._results_queue: asyncio.Queue = asyncio.Queue()
        self._session_counter = 0
        
        logging.info(f"Initialized StreamingPipelineCoordinator for session {session_id}")
    
    async def start_pipeline(self, processor_func: Callable[[ProcessingTask], Awaitable[PipelineResult]]) -> None:
        """
        Start the concurrent pipeline processing.
        
        Args:
            processor_func: Async function to process tasks through ASR->MT->TTS
        """
        if self._active:
            return
        
        self._processor_func = processor_func
        self._active = True
        
        # Start queue workers with custom processor
        await self.queue.start_workers(self._pipeline_task_processor)
        
        logging.info(f"Started pipeline for session {self.session_id}")
    
    async def stop_pipeline(self) -> None:
        """Stop pipeline processing gracefully."""
        if not self._active:
            return
        
        self._active = False
        await self.queue.stop_workers()
        
        logging.info(f"Stopped pipeline for session {self.session_id}")
    
    async def add_audio_chunk(self, audio_data: bytes, duration_ms: int, has_speech: Optional[bool] = None) -> bool:
        """
        Add audio chunk to buffer and trigger processing if segment ready.
        
        Args:
            audio_data: Raw audio bytes
            duration_ms: Duration in milliseconds
            has_speech: Whether chunk contains speech
            
        Returns:
            True if chunk was processed, False if dropped due to backpressure
        """
        if not self._active:
            return False
        
        # Add to buffer
        self.buffer.add_chunk(audio_data, duration_ms, has_speech)
        
        # Check if segment ready for processing
        segment_data = self.buffer.get_processing_segment()
        if segment_data is None:
            return True  # Buffering, no processing needed yet
        
        combined_audio, chunk_ids = segment_data
        
        # Create processing task with high priority for real-time processing
        task = ProcessingTask(
            task_id=f"{self.session_id}_{self._session_counter}",
            audio_data=combined_audio,
            session_id=self.session_id,
            timestamp=time.time(),
            priority=TaskPriority.HIGH,
            metadata={"chunk_ids": chunk_ids}
        )
        
        # Enqueue for processing (non-blocking with backpressure control)
        enqueued = await self.queue.enqueue_task(task)
        if not enqueued:
            logging.warning(f"Session {self.session_id}: Queue full when enqueuing task {task.task_id}, handling backpressure")
            # Attempt backpressure mitigation: free buffer space and retry once
            await self.handle_backpressure()
            try:
                # Small yield to allow workers to pick tasks
                await asyncio.sleep(0.05)
                enqueued = await self.queue.enqueue_task(task)
            except Exception:
                enqueued = False

        if enqueued:
            self._session_counter += 1
            # Mark chunks as processed in buffer
            self.buffer.mark_chunks_processed(chunk_ids)
        
        return enqueued
    
    async def get_next_result(self) -> Optional[PipelineResult]:
        """
        Get next completed pipeline result (non-blocking).
        
        Returns:
            PipelineResult if available, None if no results ready
        """
        try:
            result = self._results_queue.get_nowait()
            return result
        except asyncio.QueueEmpty:
            return None
    
    async def _pipeline_task_processor(self, task: ProcessingTask) -> None:
        """Process task through the pipeline with latency monitoring."""
        if not self._processor_func:
            return

        # Start session monitoring
        self.monitor.start_session()

        try:
            logging.info(
                f"[Pipeline] Session {task.session_id} - Processing chunk(s) {task.metadata.get('chunk_ids', [])} (task_id={task.task_id})"
            )

            # Process through ASR->MT->TTS pipeline
            with self.monitor.track_stage("pipeline_total"):
                result = await self._processor_func(task)

            # End session and get metrics
            session_metrics = self.monitor.end_session()

            # Add latency information to result
            result.stage_latencies = {
                stage: metrics.duration_ms
                for stage, metrics in session_metrics.items()
            }
            result.total_latency_ms = sum(result.stage_latencies.values())

            # Log step-by-step results
            logging.info(
                f"[Pipeline] Session {task.session_id} - Chunk(s) {task.metadata.get('chunk_ids', [])} processed: "
                f"success={result.success}, total_latency_ms={result.total_latency_ms:.1f}, "
                f"stage_latencies={result.stage_latencies}, error={result.error_message}"
            )
            if result.metadata:
                logging.debug(
                    f"[Pipeline] Session {task.session_id} - Result metadata: {result.metadata}"
                )

            # Put result in output queue
            await self._results_queue.put(result)

        except Exception as e:
            # Create error result
            error_result = PipelineResult(
                session_id=task.session_id,
                chunk_ids=task.metadata.get("chunk_ids", []),
                success=False,
                error_message=str(e)
            )

            # End monitoring session
            self.monitor.end_session()

            await self._results_queue.put(error_result)
            logging.error(f"Pipeline processing failed for {task.task_id}: {e}")
    
    def get_pipeline_stats(self) -> CoordinatorStats:
        """Get comprehensive statistics from all pipeline components."""
        buffer_stats = self.buffer.get_buffer_stats()
        queue_stats = self.queue.get_queue_stats()
        
        # Calculate latency statistics
        avg_latency = sum(
            self.monitor.get_stage_statistics(stage).get("avg_ms", 0.0)
            for stage in ["asr", "mt", "tts"]
        )
        
        return CoordinatorStats(
            buffer_stats=buffer_stats,
            queue_stats=queue_stats,
            latency_stats={
                "avg_total_latency_ms": avg_latency,
                "target_compliance_rate": self.monitor.get_target_compliance_rate(),
                "sessions_processed": queue_stats.get("tasks_processed", 0)
            },
            sessions_processed=queue_stats.get("tasks_processed", 0),
            avg_pipeline_latency_ms=avg_latency,
            target_compliance_rate=self.monitor.get_target_compliance_rate()
        )
    
    def is_healthy(self) -> bool:
        """Check if pipeline is operating within healthy parameters."""
        if not self._active:
            return False
        
        # Check queue health
        if self.queue.is_queue_full():
            return False
        
        # Check latency compliance
        compliance_rate = self.monitor.get_target_compliance_rate()
        if compliance_rate < 0.8:  # Less than 80% compliance
            return False
        
        return True
    
    async def handle_backpressure(self) -> None:
        """Handle backpressure by freeing buffer space and allowing queue workers to catch up."""
        if self.queue.is_queue_full():
            # Try to remove oldest half of buffered audio first to preserve recent overlap
            try:
                target = max(self.buffer.total_duration_ms // 2, 0)
                removed = 0
                while self.buffer.total_duration_ms > target and len(self.buffer.chunks) > 1:
                    oldest = self.buffer.chunks.popleft()
                    self.buffer.total_duration_ms -= oldest.duration_ms
                    removed += 1
                logging.warning(f"Backpressure detected for session {self.session_id}, removed {removed} oldest chunks")
            except Exception as e:
                logging.warning(f"Backpressure mitigation failed to trim buffer: {e}, clearing buffer instead")
                self.buffer.clear()
            # Briefly yield to let workers process queued tasks
            await asyncio.sleep(0.05)


def create_pipeline_coordinator(session_id: str, config: Optional[PipelineConfig] = None) -> StreamingPipelineCoordinator:
    """Factory function to create a pipeline coordinator."""
    return StreamingPipelineCoordinator(session_id, config)


def create_realtime_config() -> PipelineConfig:
    """Create configuration optimized for real-time sub-2s latency."""
    return PipelineConfig(
        max_buffer_duration_ms=3000,  # Smaller buffer for low latency
        chunk_size_ms=600,            # Faster chunk processing
        overlap_ms=100,               # Minimal overlap for speed
        target_latency_ms=1800.0,     # Aggressive target under 2s
        queue_size=20,                # Smaller queue for real-time
        worker_count=3,               # More workers for parallelization
        enable_parallelization=True
    )
