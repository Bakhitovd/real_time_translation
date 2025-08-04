import pytest
from hypothesis import given, strategies as st
from app.vad_sensitivity_tuner import VADSensitivityTuner

def make_chunk(energy, speech_detected, asr_transcript):
    return {
        "energy": energy,
        "speech_detected": speech_detected,
        "asr_transcript": asr_transcript,
    }

@given(
    st.lists(
        st.fixed_dictionaries({
            "energy": st.floats(min_value=0.0, max_value=1.0),
            "speech_detected": st.booleans(),
            "asr_transcript": st.text(min_size=0, max_size=10),
        }),
        min_size=5, max_size=15
    )
)
def test_update_runs_and_returns_valid_threshold(chunks):
    tuner = VADSensitivityTuner()
    threshold, log = tuner.update(chunks)
    assert 0.3 <= threshold <= 0.9
    assert "action" in log
    assert "old_threshold" in log
    assert "new_threshold" in log
    assert "false_negative_rate" in log

def test_decrease_threshold_on_false_negatives():
    tuner = VADSensitivityTuner(initial_vad_threshold=0.5, min_threshold=0.3, adjust_step=0.1, false_negative_tolerance=0.1)
    # 8/10 chunks are false negatives (energy > threshold, no speech, no transcript)
    chunks = [make_chunk(0.7, False, "") for _ in range(8)] + [make_chunk(0.2, True, "hi") for _ in range(2)]
    threshold, log = tuner.update(chunks)
    assert threshold == 0.4  # decreased by 0.1
    assert log["action"] == "decrease"

def test_increase_threshold_on_low_energy_speech():
    tuner = VADSensitivityTuner(initial_vad_threshold=0.6, max_threshold=0.9, adjust_step=0.1)
    # 8/10 chunks are low energy but marked as speech
    chunks = [make_chunk(0.2, True, "hi") for _ in range(8)] + [make_chunk(0.8, False, "") for _ in range(2)]
    threshold, log = tuner.update(chunks)
    assert threshold == 0.7  # increased by 0.1
    assert log["action"] == "increase"

def test_no_action_when_within_tolerance():
    tuner = VADSensitivityTuner(initial_vad_threshold=0.5, adjust_step=0.1, false_negative_tolerance=0.2)
    # 1/10 false negative, within tolerance, but many low-energy speech chunks (should increase threshold)
    chunks = [make_chunk(0.7, False, "")] + [make_chunk(0.2, True, "hi") for _ in range(9)]
    threshold, log = tuner.update(chunks)
    assert threshold == 0.6
    assert log["action"] == "increase"

@given(
    st.lists(
        st.fixed_dictionaries({
            "energy": st.floats(min_value=0.0, max_value=1.0),
            "speech_detected": st.booleans(),
            "asr_transcript": st.text(min_size=0, max_size=10),
        }),
        min_size=1, max_size=20
    )
)
def test_update_window_size(chunks):
    tuner = VADSensitivityTuner(window_size=5)
    # Should only consider last 5 chunks
    threshold, log = tuner.update(chunks)
    assert 0.3 <= threshold <= 0.9
    assert 1 <= log["window_size"] <= 5

def test_threshold_bounds():
    tuner = VADSensitivityTuner(initial_vad_threshold=0.9, min_threshold=0.3, max_threshold=0.9, adjust_step=0.2)
    # Try to decrease below min
    chunks = [make_chunk(1.0, False, "") for _ in range(10)]
    for _ in range(5):
        threshold, log = tuner.update(chunks)
    assert threshold == 0.3
    # Try to increase above max
    tuner = VADSensitivityTuner(initial_vad_threshold=0.3, min_threshold=0.3, max_threshold=0.9, adjust_step=0.2)
    chunks = [make_chunk(0.1, True, "hi") for _ in range(10)]
    for _ in range(5):
        threshold, log = tuner.update(chunks)
    assert threshold == 0.9
