import asyncio
import types
import pytest
from app.ws import concurrent_audio_processor
from app.realtime_queue import ProcessingTask, ProcessingResult
import time

def make_task(session_id="s1", audio_data=b"\x00"*100, task_id="t1"):
    return ProcessingTask(
        task_id=task_id,
        audio_data=audio_data,
        session_id=session_id,
        timestamp=time.time(),
        priority=1,
        metadata={}
    )

@pytest.mark.asyncio
async def test_processing_result_shape_success(monkeypatch):
    """
    Mock ASR/MT/TTS as a mix of sync/async/callable variants and verify
    concurrent_audio_processor returns a ProcessingResult with expected fields.
    """
    # Create fake modules with the expected functions. Use mixed sync/async/callable forms.
    asr_mod = types.SimpleNamespace()
    def asr_sync(audio, language=None):
        return "recognized speech"
    asr_mod.transcribe_chunk = asr_sync

    mt_mod = types.SimpleNamespace()
    async def mt_async(text, source, target, session_id=None):
        await asyncio.sleep(0)  # yield
        return "translated text"
    mt_mod.translate_text = mt_async

    tts_mod = types.SimpleNamespace()
    def tts_call_returns_coro(text):
        async def inner():
            return b"wavbytes"
        return inner()
    tts_mod.synthesize_text = tts_call_returns_coro

    # Patch importlib.import_module used inside concurrent_audio_processor to return our fakes
    import importlib
    original_import = importlib.import_module

    def fake_import(name):
        if name == "app.asr":
            return asr_mod
        if name == "app.mt":
            return mt_mod
        if name == "app.tts":
            return tts_mod
        return original_import(name)

    monkeypatch.setattr("importlib.import_module", fake_import)

    task = make_task()
    result = await concurrent_audio_processor(task)

    assert isinstance(result, ProcessingResult)
    assert result.task_id == task.task_id
    assert isinstance(result.success, bool)
    assert result.success is True
    assert isinstance(result.result_data, (bytes, bytearray))
    assert result.processing_time_ms >= 1
    assert isinstance(result.metadata, dict)
    assert result.metadata.get("transcript") == "recognized speech"
    assert result.metadata.get("translation") == "translated text"

@pytest.mark.asyncio
async def test_processing_result_shape_asr_failure(monkeypatch):
    """
    Simulate ASR producing empty transcript -> pipeline should return ProcessingResult with success=False.
    """
    asr_mod = types.SimpleNamespace()
    def asr_sync_fail(audio, language=None):
        return ""  # empty transcript

    mt_mod = types.SimpleNamespace()
    async def mt_async(text, source, target, session_id=None):
        return "should not be used"
    mt_mod.translate_text = mt_async

    tts_mod = types.SimpleNamespace()
    def tts_sync(text):
        return b"wavbytes"
    tts_mod.synthesize_text = tts_sync

    import importlib
    original_import = importlib.import_module

    def fake_import(name):
        if name == "app.asr":
            return asr_mod
        if name == "app.mt":
            return mt_mod
        if name == "app.tts":
            return tts_mod
        return original_import(name)

    monkeypatch.setattr("importlib.import_module", fake_import)

    asr_mod.transcribe_chunk = asr_sync_fail

    task = make_task(task_id="t_fail")
    result = await concurrent_audio_processor(task)

    assert isinstance(result, ProcessingResult)
    assert result.task_id == task.task_id
    assert result.success is False
    assert result.result_data is None
    assert result.error_message is not None
    assert result.processing_time_ms >= 1
    assert isinstance(result.metadata, dict)
    assert result.metadata.get("failed_stage") == "asr"
