import pytest
import time
from app.streaming_buffer import StreamingAudioBuffer, BufferConfig, AudioChunk
from app.pipeline_coordinator import StreamingPipelineCoordinator, PipelineConfig
from collections import deque

def make_dummy_chunk(duration_ms=200, content=b"\x00" * 100):
    return content, duration_ms

def test_buffer_trimming_and_handle_backpressure():
    # Small buffer config to force trimming behavior
    buf_cfg = BufferConfig(max_chunk_size_ms=500, overlap_ms=50, max_silence_gap_ms=200, max_buffer_duration_ms=800)
    buffer = StreamingAudioBuffer(buf_cfg)
    
    # Add multiple chunks to exceed buffer duration
    for i in range(6):
        data, dur = make_dummy_chunk(duration_ms=200, content=bytes([i]) * 10)
        buffer.add_chunk(data, dur, has_speech=(i % 2 == 0))
    
    # total duration should be >= max_buffer_duration_ms initially
    assert buffer.total_duration_ms >= buf_cfg.max_buffer_duration_ms
    
    # Create a coordinator and attach this buffer (monkeypatch)
    coord = StreamingPipelineCoordinator("test_session", PipelineConfig(max_buffer_duration_ms=800))
    # replace internal buffer with our buffer to test trimming
    coord.buffer = buffer
    
    # Simulate queue being full by monkeypatching queue.is_queue_full
    class DummyQueue:
        def is_queue_full(self):
            return True
    coord.queue = DummyQueue()
    
    # Record duration before backpressure
    before = buffer.total_duration_ms
    # Run backpressure handler
    import asyncio
    asyncio.get_event_loop().run_until_complete(coord.handle_backpressure())
    
    after = buffer.total_duration_ms
    # Buffer must have been trimmed or cleared
    assert after <= before
    assert after <= buf_cfg.max_buffer_duration_ms or len(buffer.chunks) <= 1
    # Ensure chunks deque remains valid
    assert isinstance(buffer.chunks, deque)
    # Ensure last chunk preserved (overlap) if more than 1 chunk remains
    if len(buffer.chunks) > 1:
        # last chunk duration should be >=0
        assert buffer.chunks[-1].duration_ms >= 0
