"""
Comprehensive tests for streaming_buffer.py module.

Tests cover buffer behavior, VAD-aware segmentation, overlap handling,
and edge cases using pytest and hypothesis for property-based testing.
"""

import pytest
import time
from unittest.mock import patch
from hypothesis import given, strategies as st, assume
from hypothesis import settings, HealthCheck

from app.streaming_buffer import (
    StreamingAudioBuffer, 
    BufferConfig, 
    AudioChunk,
    create_default_buffer
)


class TestAudioChunk:
    """Tests for AudioChunk dataclass."""
    
    def test_audio_chunk_creation(self):
        """Test AudioChunk creation with required fields."""
        chunk = AudioChunk(
            data=b"test_audio_data",
            timestamp=1234567890.0,
            duration_ms=500
        )
        assert chunk.data == b"test_audio_data"
        assert chunk.timestamp == 1234567890.0
        assert chunk.duration_ms == 500
        assert chunk.has_speech is None
        assert chunk.chunk_id == 0
    
    def test_audio_chunk_with_optional_fields(self):
        """Test AudioChunk creation with optional fields."""
        chunk = AudioChunk(
            data=b"speech_data",
            timestamp=time.time(),
            duration_ms=800,
            has_speech=True,
            chunk_id=42
        )
        assert chunk.has_speech is True
        assert chunk.chunk_id == 42


class TestBufferConfig:
    """Tests for BufferConfig dataclass."""
    
    def test_default_config(self):
        """Test BufferConfig with default values."""
        config = BufferConfig()
        assert config.max_chunk_size_ms == 1000
        assert config.overlap_ms == 200
        assert config.vad_threshold == 0.5
        assert config.max_silence_gap_ms == 500
        assert config.max_buffer_duration_ms == 5000
    
    def test_custom_config(self):
        """Test BufferConfig with custom values."""
        config = BufferConfig(
            max_chunk_size_ms=800,
            overlap_ms=150,
            vad_threshold=0.3,
            max_silence_gap_ms=400,
            max_buffer_duration_ms=4000
        )
        assert config.max_chunk_size_ms == 800
        assert config.overlap_ms == 150


class TestStreamingAudioBuffer:
    """Tests for StreamingAudioBuffer class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.config = BufferConfig(
            max_chunk_size_ms=1000,
            overlap_ms=200,
            max_silence_gap_ms=500,
            max_buffer_duration_ms=5000
        )
        self.buffer = StreamingAudioBuffer(self.config)
    
    def test_buffer_initialization(self):
        """Test buffer initialization."""
        assert len(self.buffer.chunks) == 0
        assert self.buffer.total_duration_ms == 0
        assert self.buffer.chunk_counter == 0
        assert self.buffer.last_speech_time == 0.0
    
    def test_add_single_chunk(self):
        """Test adding a single audio chunk."""
        audio_data = b"test_audio_chunk_data"
        duration = 500
        
        self.buffer.add_chunk(audio_data, duration, has_speech=True)
        
        assert len(self.buffer.chunks) == 1
        assert self.buffer.total_duration_ms == duration
        assert self.buffer.chunk_counter == 1
        assert self.buffer.chunks[0].data == audio_data
        assert self.buffer.chunks[0].duration_ms == duration
        assert self.buffer.chunks[0].has_speech is True
    
    def test_add_multiple_chunks(self):
        """Test adding multiple audio chunks."""
        chunks_data = [
            (b"chunk1", 300, True),
            (b"chunk2", 400, False),
            (b"chunk3", 250, True)
        ]
        
        for data, duration, has_speech in chunks_data:
            self.buffer.add_chunk(data, duration, has_speech)
        
        assert len(self.buffer.chunks) == 3
        assert self.buffer.total_duration_ms == 950
        assert self.buffer.chunk_counter == 3
    
    def test_buffer_trimming(self):
        """Test buffer trimming when exceeding max duration."""
        # Add chunks that exceed max buffer duration
        for i in range(10):
            self.buffer.add_chunk(f"chunk_{i}".encode(), 600, True)
        
        # Buffer should be trimmed to stay within limits
        assert self.buffer.total_duration_ms <= self.config.max_buffer_duration_ms
        assert len(self.buffer.chunks) < 10
    
    def test_segment_not_ready_insufficient_duration(self):
        """Test segment not ready when insufficient audio duration."""
        self.buffer.add_chunk(b"short_chunk", 200, True)
        
        segment = self.buffer.get_processing_segment()
        assert segment is None
    
    def test_segment_ready_sufficient_duration(self):
        """Test segment ready when sufficient audio duration."""
        self.buffer.add_chunk(b"long_chunk", 1200, True)
        
        segment = self.buffer.get_processing_segment()
        assert segment is not None
        
        audio_data, chunk_ids = segment
        assert isinstance(audio_data, bytes)
        assert isinstance(chunk_ids, list)
        assert len(chunk_ids) > 0
    
    @patch('app.streaming_buffer.time.time')
    def test_segment_ready_silence_gap(self, mock_time):
        """Test segment ready due to silence gap."""
        # Set up mock time progression: chunk creation, speech tracking, gap check
        mock_time.side_effect = [1000.0, 1000.6]  # chunk timestamp, gap check
        
        self.buffer.add_chunk(b"speech_chunk", 400, True)
        
        # Set up time for silence gap check (600ms later)
        mock_time.return_value = 1000.6
        
        segment = self.buffer.get_processing_segment()
        assert segment is not None
    
    def test_mark_chunks_processed(self):
        """Test marking chunks as processed and removal."""
        # Add multiple chunks
        for i in range(3):
            self.buffer.add_chunk(f"chunk_{i}".encode(), 400, True)
        
        initial_count = len(self.buffer.chunks)
        
        # Get segment and mark as processed
        segment = self.buffer.get_processing_segment()
        if segment:
            audio_data, chunk_ids = segment
            self.buffer.mark_chunks_processed(chunk_ids)
            
            # Some chunks should be removed (keeping overlap)
            assert len(self.buffer.chunks) < initial_count
    
    def test_buffer_stats(self):
        """Test buffer statistics generation."""
        self.buffer.add_chunk(b"test_chunk", 500, True)
        
        stats = self.buffer.get_buffer_stats()
        
        required_keys = [
            "total_chunks", "total_duration_ms", "oldest_chunk_age_ms",
            "newest_chunk_age_ms", "time_since_speech_ms", "is_segment_ready"
        ]
        
        for key in required_keys:
            assert key in stats
        
        assert stats["total_chunks"] == 1
        assert stats["total_duration_ms"] == 500
    
    def test_clear_buffer(self):
        """Test clearing all buffer contents."""
        # Add some chunks
        for i in range(3):
            self.buffer.add_chunk(f"chunk_{i}".encode(), 300, True)
        
        assert len(self.buffer.chunks) > 0
        
        self.buffer.clear()
        
        assert len(self.buffer.chunks) == 0
        assert self.buffer.total_duration_ms == 0
    
    def test_empty_buffer_operations(self):
        """Test operations on empty buffer."""
        # Empty buffer should handle operations gracefully
        assert self.buffer.get_processing_segment() is None
        
        stats = self.buffer.get_buffer_stats()
        assert stats["total_chunks"] == 0
        assert stats["oldest_chunk_age_ms"] == 0
        
        # Marking processed on empty buffer shouldn't crash
        self.buffer.mark_chunks_processed([1, 2, 3])


class TestCreateDefaultBuffer:
    """Tests for create_default_buffer function."""
    
    def test_create_default_buffer(self):
        """Test creating buffer with default optimized configuration."""
        buffer = create_default_buffer()
        
        assert isinstance(buffer, StreamingAudioBuffer)
        assert buffer.config.max_chunk_size_ms == 800
        assert buffer.config.overlap_ms == 150
        assert buffer.config.max_silence_gap_ms == 400
        assert buffer.config.max_buffer_duration_ms == 4000


class TestPropertyBasedTesting:
    """Property-based tests using Hypothesis."""
    
    @given(
        chunk_size=st.integers(min_value=100, max_value=2000),
        duration=st.integers(min_value=50, max_value=1000),
        has_speech=st.booleans()
    )
    @settings(max_examples=25, suppress_health_check=[HealthCheck.too_slow])
    def test_add_chunk_properties(self, chunk_size, duration, has_speech):
        """Property-based test for adding chunks with various parameters."""
        buffer = StreamingAudioBuffer()
        audio_data = b"x" * chunk_size
        
        initial_count = len(buffer.chunks)
        buffer.add_chunk(audio_data, duration, has_speech)
        
        # Properties that should always hold
        assert len(buffer.chunks) == initial_count + 1
        assert buffer.total_duration_ms >= duration
        assert buffer.chunk_counter > 0
        assert buffer.chunks[-1].data == audio_data
        assert buffer.chunks[-1].duration_ms == duration
        assert buffer.chunks[-1].has_speech == has_speech
    
    @given(
        num_chunks=st.integers(min_value=1, max_value=10),
        chunk_duration=st.integers(min_value=100, max_value=800)
    )
    @settings(max_examples=25, suppress_health_check=[HealthCheck.too_slow])
    def test_multiple_chunks_properties(self, num_chunks, chunk_duration):
        """Property-based test for adding multiple chunks."""
        buffer = StreamingAudioBuffer()
        
        total_expected_duration = 0
        for i in range(num_chunks):
            audio_data = f"chunk_{i}".encode()
            buffer.add_chunk(audio_data, chunk_duration, True)
            total_expected_duration += chunk_duration
        
        # Buffer may trim chunks, so total duration <= expected
        assert buffer.total_duration_ms <= total_expected_duration
        assert buffer.chunk_counter == num_chunks
        assert len(buffer.chunks) <= num_chunks  # May be trimmed
    
    @given(
        max_chunk_size=st.integers(min_value=500, max_value=2000),
        overlap=st.integers(min_value=50, max_value=500),
        max_silence_gap=st.integers(min_value=100, max_value=1000)
    )
    @settings(max_examples=25, suppress_health_check=[HealthCheck.too_slow])
    def test_config_properties(self, max_chunk_size, overlap, max_silence_gap):
        """Property-based test for buffer configuration."""
        assume(overlap < max_chunk_size)  # Overlap should be less than chunk size
        
        config = BufferConfig(
            max_chunk_size_ms=max_chunk_size,
            overlap_ms=overlap,
            max_silence_gap_ms=max_silence_gap
        )
        buffer = StreamingAudioBuffer(config)
        
        # Configuration should be preserved
        assert buffer.config.max_chunk_size_ms == max_chunk_size
        assert buffer.config.overlap_ms == overlap
        assert buffer.config.max_silence_gap_ms == max_silence_gap
        
        # Add a chunk and verify it respects configuration
        buffer.add_chunk(b"test_data", max_chunk_size + 100, True)
        
        if buffer.get_processing_segment():
            # If segment is ready, it should respect max_chunk_size constraint
            audio_data, chunk_ids = buffer.get_processing_segment()
            assert isinstance(audio_data, bytes)
            assert len(chunk_ids) > 0


@pytest.mark.integration
class TestBufferIntegration:
    """Integration tests for buffer with realistic audio scenarios."""
    
    def test_continuous_speech_processing(self):
        """Test buffer behavior with continuous speech simulation."""
        buffer = create_default_buffer()
        
        # Simulate continuous speech with 200ms chunks
        speech_chunks = [
            (b"hello", 200, True),
            (b"world", 200, True),
            (b"this", 200, True),
            (b"is", 200, True),
            (b"test", 200, True)
        ]
        
        processed_segments = []
        
        for audio_data, duration, has_speech in speech_chunks:
            buffer.add_chunk(audio_data, duration, has_speech)
            
            # Check if segment is ready for processing
            segment = buffer.get_processing_segment()
            if segment:
                processed_segments.append(segment)
                audio_data, chunk_ids = segment
                buffer.mark_chunks_processed(chunk_ids)
        
        # Should have processed at least one segment
        assert len(processed_segments) > 0
    
    def test_speech_with_silence_gaps(self):
        """Test buffer behavior with speech interrupted by silence."""
        buffer = StreamingAudioBuffer(BufferConfig(max_silence_gap_ms=300))
        
        # Add speech chunk
        with patch('app.streaming_buffer.time.time') as mock_time:
            mock_time.side_effect = [1000.0, 1000.4]  # speech chunk timestamp, gap check
            
            buffer.add_chunk(b"speech1", 400, True)
            
            # Set time for silence gap check (400ms after speech)
            mock_time.return_value = 1000.4
            
            # After silence gap, segment should be ready
            segment = buffer.get_processing_segment()
            assert segment is not None
    
    def test_buffer_performance_under_load(self):
        """Test buffer performance with high-frequency chunk additions."""
        buffer = create_default_buffer()
        
        start_time = time.time()
        
        # Add many small chunks rapidly
        for i in range(100):
            buffer.add_chunk(f"chunk_{i}".encode(), 50, i % 2 == 0)
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        # Should complete within reasonable time (< 1 second)
        assert processing_time < 1.0
        
        # Buffer should maintain reasonable size
        assert len(buffer.chunks) < 100  # Should have been trimmed
