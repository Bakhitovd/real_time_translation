"""
Tests for enhanced latency monitoring system.
"""

import pytest
import time
from unittest.mock import patch
from hypothesis import given, strategies as st, assume
from typing import Dict, List

from app.latency_monitor import (
    LatencyMonitor,
    PerformanceAnalyzer, 
    LatencyMetrics,
    OptimizationRecommendation,
    BottleneckReport,
    OptimizationCategory,
    create_latency_monitor,
    create_performance_analyzer
)


class TestLatencyMetrics:
    """Test LatencyMetrics dataclass."""
    
    def test_valid_latency_metrics(self):
        """Test creating valid LatencyMetrics."""
        metrics = LatencyMetrics(
            stage_name="asr",
            start_time=1000.0,
            end_time=1000.5,
            duration_ms=500.0,
            metadata={"confidence": 0.95}
        )
        assert metrics.stage_name == "asr"
        assert metrics.duration_ms == 500.0
        assert metrics.metadata["confidence"] == 0.95
    
    def test_negative_duration_raises_error(self):
        """Test that negative duration raises ValueError."""
        with pytest.raises(ValueError, match="Duration cannot be negative"):
            LatencyMetrics(
                stage_name="asr",
                start_time=1000.0,
                end_time=999.0,
                duration_ms=-1000.0
            )


class TestOptimizationRecommendation:
    """Test OptimizationRecommendation dataclass."""
    
    def test_valid_recommendation(self):
        """Test creating valid recommendation."""
        rec = OptimizationRecommendation(
            category=OptimizationCategory.MODEL_SELECTION,
            priority=1,
            message="Test message",
            estimated_improvement_ms=300.0,
            action_required="Test action"
        )
        assert rec.priority == 1
        assert rec.category == OptimizationCategory.MODEL_SELECTION
    
    def test_invalid_priority_raises_error(self):
        """Test that invalid priority raises ValueError."""
        with pytest.raises(ValueError, match="Priority must be 1, 2, or 3"):
            OptimizationRecommendation(
                category=OptimizationCategory.MODEL_SELECTION,
                priority=5,
                message="Test",
                estimated_improvement_ms=100.0,
                action_required="Test"
            )


class TestLatencyMonitor:
    """Test LatencyMonitor class."""
    
    @pytest.fixture
    def monitor(self):
        """Create test monitor instance."""
        return LatencyMonitor(target_latency_ms=2000.0, history_size=100)
    
    def test_monitor_initialization(self, monitor):
        """Test monitor initializes correctly."""
        assert monitor.target_latency_ms == 2000.0
        assert monitor.history_size == 100
        assert monitor._total_sessions == 0
        assert monitor._sessions_over_target == 0
    
    def test_track_stage_context_manager(self, monitor):
        """Test track_stage context manager."""
        with monitor.track_stage("test_stage", {"key": "value"}):
            time.sleep(0.01)  # Small delay for measurable duration
        
        assert "test_stage" in monitor._current_session
        metrics = monitor._current_session["test_stage"]
        assert metrics.stage_name == "test_stage"
        assert metrics.duration_ms > 0
        assert metrics.metadata["key"] == "value"
    
    def test_session_lifecycle(self, monitor):
        """Test complete session lifecycle."""
        monitor.start_session()
        
        with monitor.track_stage("stage1"):
            time.sleep(0.001)
        
        with monitor.track_stage("stage2"):
            time.sleep(0.001)
        
        session_data = monitor.end_session()
        
        assert len(session_data) == 2
        assert "stage1" in session_data
        assert "stage2" in session_data
        assert monitor._total_sessions == 1
    
    def test_target_compliance_tracking(self, monitor):
        """Test tracking of sessions exceeding target latency."""
        monitor.target_latency_ms = 10.0  # Very low target for testing
        
        monitor.start_session()
        with monitor.track_stage("slow_stage"):
            time.sleep(0.02)  # 20ms > 10ms target
        monitor.end_session()
        
        assert monitor._sessions_over_target == 1
        assert monitor.get_target_compliance_rate() == 0.0
    
    def test_stage_statistics_calculation(self, monitor):
        """Test stage statistics calculation."""
        # Add multiple measurements for a stage
        for i in range(5):
            monitor.start_session()
            with monitor.track_stage("test_stage"):
                time.sleep(0.001 * (i + 1))  # Variable delays
            monitor.end_session()
        
        stats = monitor.get_stage_statistics("test_stage")
        
        assert "avg_ms" in stats
        assert "median_ms" in stats
        assert "p95_ms" in stats
        assert "p99_ms" in stats
        assert stats["sample_count"] == 5
        assert stats["avg_ms"] > 0
    
    def test_empty_stage_statistics(self, monitor):
        """Test statistics for non-existent stage."""
        stats = monitor.get_stage_statistics("nonexistent")
        assert stats == {}
    
    def test_percentile_calculation(self):
        """Test percentile calculation method."""
        data = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        
        p50 = LatencyMonitor._calculate_percentile(data, 50)
        p95 = LatencyMonitor._calculate_percentile(data, 95)
        
        assert p50 == 5.5  # Median of 1-10
        assert abs(p95 - 9.5) < 0.1  # 95th percentile (allow floating point precision)
    
    def test_percentile_calculation_empty_data(self):
        """Test percentile calculation with empty data."""
        result = LatencyMonitor._calculate_percentile([], 50)
        assert result == 0.0
    
    @given(st.lists(st.floats(min_value=0.1, max_value=1000.0), min_size=1, max_size=100))
    def test_percentile_calculation_property(self, latencies):
        """Property-based test for percentile calculation."""
        assume(len(latencies) > 0)
        
        p0 = LatencyMonitor._calculate_percentile(latencies, 0)
        p100 = LatencyMonitor._calculate_percentile(latencies, 100)
        p50 = LatencyMonitor._calculate_percentile(latencies, 50)
        
        # P0 should be minimum, P100 should be maximum
        assert p0 == min(latencies)
        assert p100 == max(latencies)
        # P50 should be between min and max
        assert min(latencies) <= p50 <= max(latencies)


class TestPerformanceAnalyzer:
    """Test PerformanceAnalyzer class."""
    
    @pytest.fixture
    def monitor_with_data(self):
        """Create monitor with sample data."""
        monitor = LatencyMonitor(target_latency_ms=2000.0)
        
        # Add sample sessions with different patterns
        for i in range(10):
            monitor.start_session()
            
            # ASR stage - gradually increasing latency
            with monitor.track_stage("asr", {"confidence": 0.9}):
                time.sleep(0.001 * (i + 5))
            
            # MT stage - consistent latency  
            with monitor.track_stage("mt"):
                time.sleep(0.001 * 2)
            
            # TTS stage - low latency
            with monitor.track_stage("tts"):
                time.sleep(0.001)
            
            monitor.end_session()
        
        return monitor
    
    @pytest.fixture
    def analyzer(self, monitor_with_data):
        """Create analyzer with test data."""
        return PerformanceAnalyzer(monitor_with_data)
    
    def test_analyzer_initialization(self, monitor_with_data):
        """Test analyzer initializes correctly."""
        analyzer = PerformanceAnalyzer(monitor_with_data)
        assert analyzer.monitor is monitor_with_data
    
    def test_bottleneck_analysis(self, analyzer):
        """Test bottleneck analysis functionality."""
        report = analyzer.analyze_bottlenecks(recent_sessions=5)
        
        assert isinstance(report, BottleneckReport)
        assert report.primary_bottleneck in ["asr", "mt", "tts"]
        assert len(report.avg_stage_latencies) > 0
        assert report.total_sessions_analyzed <= 5
        assert isinstance(report.recommendations, list)
    
    def test_optimization_recommendations_high_asr_latency(self):
        """Test recommendations for high ASR latency."""
        monitor = LatencyMonitor()
        
        # Create sessions with high ASR latency
        for _ in range(3):
            monitor.start_session()
            with monitor.track_stage("asr"):
                time.sleep(0.001)  # Simulate 1ms, but we'll mock the stats
            monitor.end_session()
        
        analyzer = PerformanceAnalyzer(monitor)
        
        # Mock high ASR latency
        with patch.object(monitor, 'get_stage_statistics') as mock_stats:
            mock_stats.return_value = {"avg_ms": 900.0}
            recommendations = analyzer.get_optimization_recommendations()
            
            # Should recommend smaller Whisper model
            asr_recs = [r for r in recommendations if "ASR" in r.message]
            assert len(asr_recs) > 0
            assert asr_recs[0].priority == 1
    
    def test_optimization_recommendations_low_compliance(self):
        """Test recommendations for low target compliance."""
        monitor = LatencyMonitor(target_latency_ms=100.0)  # Very low target
        
        # Create sessions that exceed target
        for _ in range(5):
            monitor.start_session()
            with monitor.track_stage("test"):
                time.sleep(0.2)  # 200ms > 100ms target
            monitor.end_session()
        
        analyzer = PerformanceAnalyzer(monitor)
        recommendations = analyzer.get_optimization_recommendations()
        
        # Should recommend system resources investigation
        compliance_recs = [r for r in recommendations if "sessions meet target" in r.message]
        assert len(compliance_recs) > 0
        assert compliance_recs[0].priority == 1
    
    @given(st.integers(min_value=1, max_value=50))
    def test_analyze_bottlenecks_with_varying_sessions(self, num_sessions):
        """Property-based test for bottleneck analysis with varying session counts."""
        monitor = LatencyMonitor()
        
        # Add random sessions
        for i in range(num_sessions):
            monitor.start_session()
            with monitor.track_stage("test_stage"):
                time.sleep(0.001)
            monitor.end_session()
        
        analyzer = PerformanceAnalyzer(monitor)
        report = analyzer.analyze_bottlenecks(recent_sessions=num_sessions)
        
        # Basic invariants
        assert report.total_sessions_analyzed <= num_sessions
        assert isinstance(report.recommendations, list)
        if report.avg_stage_latencies:
            assert all(latency >= 0 for latency in report.avg_stage_latencies.values())


class TestFactoryFunctions:
    """Test factory functions."""
    
    def test_create_latency_monitor(self):
        """Test latency monitor factory function."""
        monitor = create_latency_monitor(target_ms=1500.0, history_size=500)
        
        assert isinstance(monitor, LatencyMonitor)
        assert monitor.target_latency_ms == 1500.0
        assert monitor.history_size == 500
    
    def test_create_performance_analyzer(self):
        """Test performance analyzer factory function."""
        monitor = create_latency_monitor()
        analyzer = create_performance_analyzer(monitor)
        
        assert isinstance(analyzer, PerformanceAnalyzer)
        assert analyzer.monitor is monitor


class TestIntegrationScenarios:
    """Test realistic integration scenarios."""
    
    def test_realistic_translation_pipeline_simulation(self):
        """Test simulation of realistic translation pipeline."""
        monitor = create_latency_monitor(target_ms=2000.0)
        analyzer = create_performance_analyzer(monitor)
        
        # Simulate 20 translation sessions
        for session_id in range(20):
            monitor.start_session()
            
            # Audio conversion stage
            with monitor.track_stage("conversion", {"input_format": "webm"}):
                time.sleep(0.01)  # 10ms
            
            # ASR stage with varying confidence
            confidence = 0.8 + (session_id % 5) * 0.04  # 0.8 to 0.96
            with monitor.track_stage("asr", {"confidence": confidence}):
                time.sleep(0.05)  # 50ms
            
            # MT stage
            with monitor.track_stage("mt", {"source": "ru", "target": "en"}):
                time.sleep(0.03)  # 30ms
            
            # TTS stage
            with monitor.track_stage("tts", {"voice_id": "test_voice"}):
                time.sleep(0.04)  # 40ms
            
            monitor.end_session()
        
        # Analyze results
        report = analyzer.analyze_bottlenecks()
        
        assert report.total_sessions_analyzed == 20
        assert len(report.avg_stage_latencies) == 4
        assert report.primary_bottleneck in ["conversion", "asr", "mt", "tts"]
        
        # All sessions should meet 2s target with these timings
        compliance_rate = monitor.get_target_compliance_rate()
        assert compliance_rate == 1.0
    
    @given(
        st.lists(
            st.floats(min_value=10.0, max_value=100.0), 
            min_size=5, 
            max_size=15
        )
    )
    def test_property_based_session_analysis(self, asr_latencies):
        """Property-based test for session analysis with random ASR latencies."""
        assume(len(asr_latencies) >= 5)
        
        monitor = create_latency_monitor(target_ms=2000.0)
        
        # Create sessions with simulated latencies (without actual sleep for speed)
        for latency_ms in asr_latencies:
            monitor.start_session()
            # Simulate timing by directly creating metrics
            start_time = time.time()
            end_time = start_time + (latency_ms / 1000.0)
            metrics = LatencyMetrics(
                stage_name="asr",
                start_time=start_time,
                end_time=end_time,
                duration_ms=latency_ms
            )
            monitor._current_session["asr"] = metrics
            monitor.end_session()
        
        # Analyze statistics
        stats = monitor.get_stage_statistics("asr")
        
        # Verify statistical properties
        assert stats["sample_count"] == len(asr_latencies)
        assert abs(stats["min_ms"] - min(asr_latencies)) < 0.1  # Should be exact
        assert abs(stats["max_ms"] - max(asr_latencies)) < 0.1
        assert stats["avg_ms"] > 0
        assert stats["p95_ms"] >= stats["median_ms"]
    
    def test_performance_degradation_detection(self):
        """Test detection of performance degradation over time."""
        monitor = create_latency_monitor(target_ms=500.0)  # Strict target for testing
        analyzer = create_performance_analyzer(monitor)
        
        # Simulate gradual performance degradation
        base_latency = 0.2  # 200ms base
        for i in range(15):
            monitor.start_session()
            
            # Gradually increasing latency (simulating memory leak or resource exhaustion)  
            current_latency = base_latency + (i * 0.05)  # Increases by 50ms each session
            
            with monitor.track_stage("degrading_stage"):
                time.sleep(current_latency)
            
            monitor.end_session()
        
        # Later sessions should exceed target (200ms + 14*50ms = 900ms > 500ms target)
        compliance_rate = monitor.get_target_compliance_rate()
        assert compliance_rate < 1.0  # Some sessions should exceed 500ms target
        assert compliance_rate < 0.90  # Should trigger compliance recommendation
        
        # Should generate recommendations
        recommendations = analyzer.get_optimization_recommendations()
        assert len(recommendations) > 0
        
        # Should identify the issue
        system_recs = [r for r in recommendations 
                      if r.category == OptimizationCategory.SYSTEM_RESOURCES]
        assert len(system_recs) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
