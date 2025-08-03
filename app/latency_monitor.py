"""
Enhanced latency monitoring for real-time speech translation pipeline.
Tracks performance, identifies bottlenecks, and provides optimization recommendations.
"""

import time
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, ContextManager
from contextlib import contextmanager
from enum import Enum
import statistics
from collections import deque, defaultdict


class OptimizationCategory(Enum):
    MODEL_SELECTION = "model_selection"
    QUEUE_TUNING = "queue_tuning" 
    CHUNK_STRATEGY = "chunk_strategy"
    SYSTEM_RESOURCES = "system_resources"


@dataclass
class LatencyMetrics:
    """Represents timing data for a single pipeline stage."""
    stage_name: str
    start_time: float
    end_time: float
    duration_ms: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if self.duration_ms < 0:
            raise ValueError(f"Duration cannot be negative: {self.duration_ms}")


@dataclass
class OptimizationRecommendation:
    """Actionable recommendation for performance improvement."""
    category: OptimizationCategory
    priority: int  # 1=critical, 2=important, 3=nice-to-have
    message: str
    estimated_improvement_ms: float
    action_required: str
    
    def __post_init__(self):
        if self.priority not in [1, 2, 3]:
            raise ValueError(f"Priority must be 1, 2, or 3: {self.priority}")


@dataclass
class BottleneckReport:
    """Analysis of pipeline performance bottlenecks."""
    primary_bottleneck: str
    avg_stage_latencies: Dict[str, float]
    p95_total_latency: float
    sessions_over_target: int
    recommendations: List[OptimizationRecommendation]
    total_sessions_analyzed: int


class LatencyMonitor:
    """Real-time latency monitoring for translation pipeline."""
    
    def __init__(self, target_latency_ms: float = 2000.0, history_size: int = 1000):
        self.target_latency_ms = target_latency_ms
        self.history_size = history_size
        
        # Current session tracking
        self._current_session: Dict[str, LatencyMetrics] = {}
        self._session_start_time: Optional[float] = None
        
        # Historical data
        self._historical_sessions: deque = deque(maxlen=history_size)
        self._stage_latencies: Dict[str, deque] = defaultdict(lambda: deque(maxlen=history_size))
        
        # Performance statistics
        self._total_sessions = 0
        self._sessions_over_target = 0
    
    @contextmanager
    def track_stage(self, stage_name: str, metadata: Optional[Dict[str, Any]] = None) -> ContextManager[None]:
        """Context manager to track latency for a pipeline stage."""
        if metadata is None:
            metadata = {}
            
        start_time = time.time()
        
        try:
            yield
        finally:
            end_time = time.time()
            duration_ms = (end_time - start_time) * 1000
            
            metrics = LatencyMetrics(
                stage_name=stage_name,
                start_time=start_time,
                end_time=end_time,
                duration_ms=duration_ms,
                metadata=metadata
            )
            
            self._current_session[stage_name] = metrics
    
    def start_session(self) -> None:
        """Start tracking a new pipeline session."""
        self._current_session.clear()
        self._session_start_time = time.time()
    
    def end_session(self) -> Dict[str, LatencyMetrics]:
        """End current session and store results."""
        if not self._current_session:
            return {}
        
        # Calculate total session time
        if self._session_start_time:
            total_duration = (time.time() - self._session_start_time) * 1000
            if total_duration > self.target_latency_ms:
                self._sessions_over_target += 1
        
        # Store session data
        session_copy = self._current_session.copy()
        self._historical_sessions.append(session_copy)
        
        # Update stage-specific data
        for stage_name, metrics in session_copy.items():
            self._stage_latencies[stage_name].append(metrics.duration_ms)
        
        self._total_sessions += 1
        self._current_session.clear()
        self._session_start_time = None
        
        return session_copy
    
    def get_stage_statistics(self, stage_name: str) -> Dict[str, float]:
        """Get statistical summary for a specific stage."""
        if stage_name not in self._stage_latencies:
            return {}
        
        latencies = list(self._stage_latencies[stage_name])
        if not latencies:
            return {}
        
        return {
            "avg_ms": statistics.mean(latencies),
            "median_ms": statistics.median(latencies),
            "p95_ms": self._calculate_percentile(latencies, 95),
            "p99_ms": self._calculate_percentile(latencies, 99),
            "min_ms": min(latencies),
            "max_ms": max(latencies),
            "sample_count": len(latencies)
        }
    
    def get_target_compliance_rate(self) -> float:
        """Get percentage of sessions meeting target latency."""
        if self._total_sessions == 0:
            return 1.0
        return 1.0 - (self._sessions_over_target / self._total_sessions)
    
    @staticmethod
    def _calculate_percentile(data: List[float], percentile: int) -> float:
        """Calculate percentile value from data."""
        if not data:
            return 0.0
        sorted_data = sorted(data)
        index = (percentile / 100) * (len(sorted_data) - 1)
        if index.is_integer():
            return sorted_data[int(index)]
        else:
            lower = sorted_data[int(index)]
            upper = sorted_data[int(index) + 1]
            return lower + (upper - lower) * (index - int(index))


class PerformanceAnalyzer:
    """Analyzes performance data and provides optimization recommendations."""
    
    def __init__(self, monitor: LatencyMonitor):
        self.monitor = monitor
    
    def analyze_bottlenecks(self, recent_sessions: int = 50) -> BottleneckReport:
        """Identify performance bottlenecks in the pipeline."""
        stage_stats = {}
        total_latencies = []
        
        # Collect statistics for all stages
        for stage_name in self.monitor._stage_latencies:
            stats = self.monitor.get_stage_statistics(stage_name)
            if stats:
                stage_stats[stage_name] = stats["avg_ms"]
        
        # Calculate total latencies from recent sessions
        recent_sessions_data = list(self.monitor._historical_sessions)[-recent_sessions:]
        for session in recent_sessions_data:
            total_latency = sum(metrics.duration_ms for metrics in session.values())
            total_latencies.append(total_latency)
        
        # Identify primary bottleneck
        primary_bottleneck = max(stage_stats.items(), key=lambda x: x[1])[0] if stage_stats else "unknown"
        
        # Calculate P95 total latency
        p95_total = self.monitor._calculate_percentile(total_latencies, 95) if total_latencies else 0.0
        
        # Generate recommendations
        recommendations = self.get_optimization_recommendations()
        
        return BottleneckReport(
            primary_bottleneck=primary_bottleneck,
            avg_stage_latencies=stage_stats,
            p95_total_latency=p95_total,
            sessions_over_target=self.monitor._sessions_over_target,
            recommendations=recommendations,
            total_sessions_analyzed=len(recent_sessions_data)
        )
    
    def get_optimization_recommendations(self) -> List[OptimizationRecommendation]:
        """Generate actionable optimization recommendations."""
        recommendations = []
        
        # Check for high ASR latency
        asr_stats = self.monitor.get_stage_statistics("asr")
        if asr_stats and asr_stats["avg_ms"] > 800:
            recommendations.append(OptimizationRecommendation(
                category=OptimizationCategory.MODEL_SELECTION,
                priority=1,
                message="ASR latency too high, consider using smaller Whisper model",
                estimated_improvement_ms=300.0,
                action_required="Switch to Whisper 'small' or 'medium' model"
            ))
        
        # Check for MT latency issues
        mt_stats = self.monitor.get_stage_statistics("mt")
        if mt_stats and mt_stats["avg_ms"] > 500:
            recommendations.append(OptimizationRecommendation(
                category=OptimizationCategory.MODEL_SELECTION,
                priority=2,
                message="Machine translation latency elevated",
                estimated_improvement_ms=200.0,
                action_required="Consider local MT model or optimize API calls"
            ))
        
        # Check target compliance
        compliance_rate = self.monitor.get_target_compliance_rate()
        if compliance_rate < 0.90:
            recommendations.append(OptimizationRecommendation(
                category=OptimizationCategory.SYSTEM_RESOURCES,
                priority=1,
                message=f"Only {compliance_rate:.1%} sessions meet target latency",
                estimated_improvement_ms=500.0,
                action_required="Investigate system resources and optimize bottlenecks"
            ))
        
        return sorted(recommendations, key=lambda r: r.priority)


def create_latency_monitor(target_ms: float = 2000.0, history_size: int = 1000) -> LatencyMonitor:
    """Factory function to create a LatencyMonitor instance."""
    return LatencyMonitor(target_latency_ms=target_ms, history_size=history_size)


def create_performance_analyzer(monitor: LatencyMonitor) -> PerformanceAnalyzer:
    """Factory function to create a PerformanceAnalyzer instance."""
    return PerformanceAnalyzer(monitor)
