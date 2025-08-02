"""
Streaming Audio Buffer Module for Real-time Speech Translation.

Handles circular audio buffering, VAD-aware segmentation, and overlap management
for continuous transcription in sub-2 second latency scenarios.
"""

import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Optional, List, Tuple, Iterator
import numpy as np


@dataclass
class AudioChunk:
    """Represents a chunk of audio data with metadata."""
    data: bytes
    timestamp: float
    duration_ms: int
    has_speech: Optional[bool] = None
    chunk_id: int = 0


@dataclass
class BufferConfig:
    """Configuration for streaming buffer behavior."""
    max_chunk_size_ms: int = 1000  # Maximum chunk size in milliseconds
    overlap_ms: int = 200  # Overlap between chunks for continuity
    vad_threshold: float = 0.5  # Voice activity detection threshold
    max_silence_gap_ms: int = 500  # Max silence before finalizing segment
    max_buffer_duration_ms: int = 5000  # Maximum total buffer duration


class StreamingAudioBuffer:
    """
    Circular buffer for managing streaming audio chunks with VAD-aware segmentation.
    
    Optimized for real-time translation with sub-2 second latency requirements.
    """
    
    def __init__(self, config: Optional[BufferConfig] = None):
        """Initialize streaming buffer with configuration."""
        self.config = config or BufferConfig()
        self.chunks: deque[AudioChunk] = deque()
        self.total_duration_ms = 0
        self.chunk_counter = 0
        self.last_speech_time = 0.0
        self.current_segment_chunks: List[AudioChunk] = []
        
        logging.info(f"Initialized StreamingAudioBuffer with {self.config}")
    
    def add_chunk(self, audio_data: bytes, duration_ms: int, has_speech: Optional[bool] = None) -> None:
        """
        Add new audio chunk to the buffer.
        
        Args:
            audio_data: Raw audio bytes
            duration_ms: Duration of the chunk in milliseconds
            has_speech: Whether chunk contains speech (None for auto-detect)
        """
        timestamp = time.time()
        chunk = AudioChunk(
            data=audio_data,
            timestamp=timestamp,
            duration_ms=duration_ms,
            has_speech=has_speech,
            chunk_id=self.chunk_counter
        )
        
        self.chunks.append(chunk)
        self.total_duration_ms += duration_ms
        self.chunk_counter += 1
        
        # Track speech activity
        if has_speech:
            self.last_speech_time = timestamp
        
        # Maintain buffer size limit
        self._trim_buffer()
        
        logging.debug(f"Added chunk {chunk.chunk_id}: {len(audio_data)} bytes, "
                     f"duration={duration_ms}ms, speech={has_speech}")
    
    def get_processing_segment(self) -> Optional[Tuple[bytes, List[int]]]:
        """
        Get the next segment ready for processing with overlap handling.
        
        Returns:
            Tuple of (combined_audio_bytes, chunk_ids) or None if no segment ready
        """
        if not self._is_segment_ready():
            return None
        
        # Collect chunks for processing
        segment_chunks = self._collect_segment_chunks()
        if not segment_chunks:
            return None
        
        # Combine audio data with overlap
        combined_audio = self._combine_chunks_with_overlap(segment_chunks)
        chunk_ids = [chunk.chunk_id for chunk in segment_chunks]
        
        logging.debug(f"Created processing segment with {len(segment_chunks)} chunks, "
                     f"IDs: {chunk_ids}")
        
        return combined_audio, chunk_ids
    
    def mark_chunks_processed(self, chunk_ids: List[int]) -> None:
        """Mark chunks as processed and remove from buffer."""
        # Remove processed chunks (keep overlap for next segment)
        chunks_to_remove = []
        for chunk in self.chunks:
            if chunk.chunk_id in chunk_ids[:-1]:  # Keep last chunk for overlap
                chunks_to_remove.append(chunk)
        
        for chunk in chunks_to_remove:
            self.chunks.remove(chunk)
            self.total_duration_ms -= chunk.duration_ms
        
        logging.debug(f"Removed {len(chunks_to_remove)} processed chunks")
    
    def _is_segment_ready(self) -> bool:
        """Check if buffer has a segment ready for processing."""
        if not self.chunks:
            return False
        
        # Check if buffer is getting full (highest priority)
        if self.total_duration_ms >= self.config.max_buffer_duration_ms:
            return True
        
        # Check if we have enough audio duration for processing
        if self.total_duration_ms >= self.config.max_chunk_size_ms:
            return True
        
        # Check for silence gap (indicates end of utterance)
        if self.last_speech_time > 0:  # Only check if we've had speech
            time_since_speech = time.time() - self.last_speech_time
            silence_gap_ms = time_since_speech * 1000
            
            if silence_gap_ms > self.config.max_silence_gap_ms:
                return True
        
        return False
    
    def _collect_segment_chunks(self) -> List[AudioChunk]:
        """Collect chunks that form a processing segment."""
        if not self.chunks:
            return []
        
        segment_chunks = []
        accumulated_duration = 0
        
        for chunk in self.chunks:
            segment_chunks.append(chunk)
            accumulated_duration += chunk.duration_ms
            
            # Stop if we have enough duration for processing
            if accumulated_duration >= self.config.max_chunk_size_ms:
                break
        
        return segment_chunks
    
    def _combine_chunks_with_overlap(self, chunks: List[AudioChunk]) -> bytes:
        """Combine multiple audio chunks with overlap handling."""
        if not chunks:
            return b""
        
        if len(chunks) == 1:
            return chunks[0].data
        
        # Simple concatenation for now - could be enhanced with proper audio mixing
        combined = b""
        for chunk in chunks:
            combined += chunk.data
        
        return combined
    
    def _trim_buffer(self) -> None:
        """Remove old chunks to maintain buffer size limits."""
        while (self.total_duration_ms > self.config.max_buffer_duration_ms and 
               len(self.chunks) > 1):
            oldest_chunk = self.chunks.popleft()
            self.total_duration_ms -= oldest_chunk.duration_ms
            
            logging.debug(f"Trimmed oldest chunk {oldest_chunk.chunk_id}")
    
    def get_buffer_stats(self) -> dict:
        """Get current buffer statistics for monitoring."""
        return {
            "total_chunks": len(self.chunks),
            "total_duration_ms": self.total_duration_ms,
            "oldest_chunk_age_ms": (time.time() - self.chunks[0].timestamp) * 1000 if self.chunks else 0,
            "newest_chunk_age_ms": (time.time() - self.chunks[-1].timestamp) * 1000 if self.chunks else 0,
            "time_since_speech_ms": (time.time() - self.last_speech_time) * 1000,
            "is_segment_ready": self._is_segment_ready()
        }
    
    def clear(self) -> None:
        """Clear all buffered chunks."""
        self.chunks.clear()
        self.total_duration_ms = 0
        self.current_segment_chunks.clear()
        logging.info("Buffer cleared")


def create_default_buffer() -> StreamingAudioBuffer:
    """Create a streaming buffer with default configuration optimized for sub-2s latency."""
    config = BufferConfig(
        max_chunk_size_ms=800,  # Slightly smaller for faster processing
        overlap_ms=150,  # Reduce overlap for speed
        max_silence_gap_ms=400,  # Faster segment finalization
        max_buffer_duration_ms=4000  # Smaller buffer for memory efficiency
    )
    return StreamingAudioBuffer(config)
