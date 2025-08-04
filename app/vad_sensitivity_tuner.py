"""
vad_sensitivity_tuner.py

Micro-unit module for adaptive VAD/ASR sensitivity tuning in real-time speech pipelines.

- Pure function/class, ≤150 LOC, no external I/O.
- Dynamically adjusts VAD/ASR thresholds based on recent chunk metadata and ASR/VAD results.
- Designed for integration with StreamingAudioBuffer or ASR pre-processing.
- Logs tuning actions via return values (no side effects).

Author: Cline (2025-08-03)
"""

from typing import List, Dict, Optional, Tuple

class VADSensitivityTuner:
    """
    Adaptive VAD/ASR sensitivity tuner.

    Usage:
        tuner = VADSensitivityTuner(
            initial_vad_threshold=0.6,
            min_threshold=0.3,
            max_threshold=0.9,
            window_size=10,
            false_negative_tolerance=0.2,
            adjust_step=0.05,
        )
        new_threshold, log = tuner.update(
            recent_chunks=[
                {"energy": 0.12, "speech_detected": False, "asr_transcript": ""},
                {"energy": 0.25, "speech_detected": True, "asr_transcript": "hello"},
                ...
            ]
        )
    """

    def __init__(
        self,
        initial_vad_threshold: float = 0.6,
        min_threshold: float = 0.3,
        max_threshold: float = 0.9,
        window_size: int = 10,
        false_negative_tolerance: float = 0.2,
        adjust_step: float = 0.05,
    ):
        self.vad_threshold = initial_vad_threshold
        self.min_threshold = min_threshold
        self.max_threshold = max_threshold
        self.window_size = window_size
        self.false_negative_tolerance = false_negative_tolerance
        self.adjust_step = adjust_step

    def update(
        self,
        recent_chunks: List[Dict[str, Optional[object]]]
    ) -> Tuple[float, Dict[str, object]]:
        """
        Analyze recent chunk metadata and adapt VAD threshold.

        Args:
            recent_chunks: List of dicts, each with:
                - "energy": float, mean energy of chunk (0..1)
                - "speech_detected": bool, VAD result
                - "asr_transcript": str, ASR output (empty if none)

        Returns:
            new_threshold: float, updated VAD threshold
            log: dict, tuning action and stats
        """
        # Only consider last window_size chunks
        window = recent_chunks[-self.window_size:] if len(recent_chunks) > self.window_size else recent_chunks

        # False negative: high energy, no speech detected, empty transcript
        false_negatives = [
            c for c in window
            if c.get("energy", 0) > self.vad_threshold
            and not c.get("speech_detected", False)
            and not c.get("asr_transcript", "")
        ]
        false_negative_rate = len(false_negatives) / max(1, len(window))

        # If too many false negatives, lower threshold (more sensitive)
        action = "none"
        old_threshold = self.vad_threshold
        if false_negative_rate > self.false_negative_tolerance:
            self.vad_threshold = max(self.min_threshold, self.vad_threshold - self.adjust_step)
            action = "decrease"
        # If no false negatives and many low-energy chunks marked as speech, increase threshold
        else:
            low_energy_speech = [
                c for c in window
                if c.get("energy", 0) < self.vad_threshold * 0.7
                and c.get("speech_detected", False)
            ]
            if len(low_energy_speech) > len(window) * 0.5:
                self.vad_threshold = min(self.max_threshold, self.vad_threshold + self.adjust_step)
                action = "increase"

        return self.vad_threshold, {
            "action": action,
            "old_threshold": old_threshold,
            "new_threshold": self.vad_threshold,
            "false_negative_rate": false_negative_rate,
            "window_size": len(window),
            "false_negatives": len(false_negatives),
        }
