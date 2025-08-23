# Implementation Plan

[Overview]
Stabilize and harden the existing real-time speech translation pipeline, fix correctness and latency bugs (especially VAD duration wiring and backpressure), add robust normalization for mixed sync/async mocks, improve resilience in ASR/MT/TTS components, and produce a tuning guide and tests so the system can be validated and tuned locally.

This plan describes targeted, incremental changes that preserve the current architecture (FastAPI WebSocket API, asyncio pipeline, faster-whisper ASR, M2M/OpenAI MT, pyttsx3/Coqui TTS) while addressing correctness, backpressure, timing, and test stability issues discovered during investigation. The scope focuses on stabilizing existing modules, adding small helper utilities, and extending tests and documentation so a maintainer or the original author can re-run and tune the system locally without live audio I/O. Changes are intentionally scoped to individual modules with small, testable modifications and clear migration steps.

[Types]  
Introduce and standardize a small set of types and data shapes used across the pipeline to remove ambiguity between tests and runtime:

- ProcessingTask (existing, app/realtime_queue.py)
  - task_id: str
  - audio_data: bytes
  - session_id: str
  - timestamp: float (POSIX)
  - priority: TaskPriority (enum)
  - metadata: Dict[str, Any]
  - Validation rules: non-empty task_id & session_id, timestamp > 0

- ProcessingResult (existing, app/realtime_queue.py)
  - task_id: str
  - success: bool
  - result_data: Optional[bytes] (synthesized audio bytes on success)
  - error_message: Optional[str]
  - processing_time_ms: float >= 0
  - metadata: Dict[str, Any] (keys used by tests/runtime: "transcript", "translation", "failed_stage", "stage_latencies")
  - Validation rules: processing_time_ms must be numeric and non-negative; metadata may include nested dicts and lists.

- PipelineConfig (existing, app/pipeline_coordinator.py)
  - max_buffer_duration_ms: int > 0
  - chunk_size_ms: int > 0
  - overlap_ms: int >= 0
  - target_latency_ms: float > 0
  - queue_size: int > 0
  - worker_count: int > 0
  - enable_parallelization: bool

- PipelineResult (existing, app/pipeline_coordinator.py)
  - session_id: str
  - chunk_ids: List[int]
  - translated_audio: Optional[bytes]
  - success: bool
  - stage_latencies: Dict[str, float] (ms)
  - total_latency_ms: float
  - error_message: Optional[str]
  - metadata: Dict[str, Any]

- AudioChunk (existing, app/streaming_buffer.py)
  - data: bytes, timestamp: float, duration_ms: int, has_speech: Optional[bool], chunk_id: int

- BufferConfig / QueueConfig (existing)
  - Describe expected fields and validation constraints (see files for full fields).

- Helper semantics:
  - _ensure_resolved(value) semantics: Accept a value that may be a coroutine/awaitable, a callable returning a value/awaitable, or a plain value. The function returns the final resolved non-awaitable value or string fallback, and should be tested for nested awaitables/callables (up to a small depth).

[Files]
Describe file-level changes precisely. Paths are relative to repository root.

Single sentence: Update existing modules to improve robustness, add tests and documentation, and add small helpers.

Detailed breakdown:
- New files to be created
  - docs/tuning_guide.md — Purpose: detailed step-by-step local tuning guide, recommended hyperparameters, commands to run scripts/tune_parameters.py, and examples interpreting outputs.
  - tests/test_ensure_resolved.py — Purpose: unit & hypothesis tests for _ensure_resolved helper; validate behavior with sync values, callables, coroutines, nested combinations (≥25 randomized combinations).
  - tests/test_backpressure_trimming.py — Purpose: tests for StreamingPipelineCoordinator.handle_backpressure trimming strategy and StreamingAudioBuffer trimming invariants under load.
  - tests/test_processing_result_shapes.py — Purpose: ensure concurrent_audio_processor returns ProcessingResult with expected fields and value constraints.
  - docs/change_log_pr_summary.md — Purpose: concise summary of changes for maintainers (optional but recommended).

- Existing files to be modified (with specific changes)
  - app/ws.py
    - Ensure detect_speech_activity returns a two-tuple: (bool has_speech, dict metadata) where metadata contains "duration_ms". Remove any code that attempted to unpack a third return value.
    - Replace direct calls to detect_speech_activity(...) = has_speech, vad_metadata, vad_duration_ms with the two-value return and extract duration_ms from metadata safely.
    - Ensure concurrent_audio_processor returns app.realtime_queue.ProcessingResult (or PipelineResult when passed through coordinator) with fields: task_id, success, result_data (audio bytes), error_message, processing_time_ms (≥1ms), metadata (include transcript/translation/failed_stage/stage_latencies).
    - Use _ensure_resolved consistently to normalize values returned by possibly-mocked functions before string operations (strip()).
    - Avoid brittle attribute access on result objects (use dict.get or safe attribute checks) matching tests.
    - Minimal changes to websocket_translate: use the PipelineResult fields produced by coordinator rather than expecting custom fields. Ensure compatibility with tests (see get_next_result handling).

  - app/pipeline_coordinator.py
    - Keep PipelineConfig but ensure StreamingPipelineCoordinator._pipeline_task_processor accepts ProcessingResult or PipelineResult and maps fields into PipelineResult for downstream websocket handling.
    - Ensure stage_latencies and total_latency_ms are always present in the PipelineResult produced by coordinator (empty dict / 0.0 fallback).
    - Confirm create_realtime_config values are conservative and match tests (no changes unless necessary).

  - app/asr.py
    - Harden transcribe_chunk to:
      - Validate WAV header via validate_wav_format; don't fail hard on invalid WAV but log and return empty transcript.
      - Always return a string (possibly empty) and never a coroutine.
      - Avoid blocking long sleeps; use small backoffs for retries.

  - app/mt.py
    - Ensure translate_text (convenience function) returns a string and is an async function (already is).
    - Confirm circuit breaker & retry params are read from config.yaml; add missing keys to config.yaml if absent.

  - app/tts.py
    - Ensure synthesize_text returns bytes (empty bytes on failure) and never a coroutine.
    - Keep thread-safety and timeouts, but avoid calling engine.runAndWait on main thread; maintain current approach.

  - app/realtime_queue.py
    - Ensure ProcessingResult dataclass is consistent with tests: field names and types must match test expectations (processing_time_ms present and numeric).
    - Ensure enqueue_task returns False when the queue is full without raising unexpected exceptions.

  - app/streaming_buffer.py
    - Ensure get_processing_segment returns Tuple[bytes, List[int]] OR None and that mark_chunks_processed preserves last chunk for overlap.
    - Ensure total_duration_ms maintained and trimmed correctly.

  - config.yaml
    - Add/configure an "translation.m2m_service" section with:
      - url, timeout_seconds, max_retries, failure_threshold, circuit_open_duration, backoff_base, max_backoff
    - Add any test-run friendly flags (e.g., enable_mock_mt: true) if missing (only if necessary and safe).

  - scripts/tune_parameters.py
    - Keep the script (exists) but ensure it is referenced from docs/tuning_guide.md and supports running through the pipeline offline using sample audio files in input_audio/.

- Files to be deleted or moved
  - None recommended. Keep history.

[Functions]
Single sentence: Introduce small helper normalization and tighten function contracts for ASR/MT/TTS and pipeline processors; adapt existing functions to guarantee return types and metadata.

Detailed breakdown:
- New functions
  - _ensure_resolved(value, max_iter=3) -> Any (app/ws.py)
    - Purpose: Normalize mixed sync/async/callable return values in tests & runtime.
    - Behavior: Unwrap awaitables and callables (no args) up to max_iter times, return final value or string fallback on error.
  - validate_processing_result_shape(result) -> bool (tests helper in tests/)  
    - Purpose: Confirm ProcessingResult has required fields with correct types.

- Modified functions
  - app/ws.py: detect_speech_activity(audio_data: bytes, sensitivity: float = 0.8) -> tuple[bool, dict]
    - Change: ensure two-value return, metadata contains duration_ms; never return three separate values.
    - Adjust call-sites to read duration_ms as metadata.get("duration_ms", 0).
  - app/ws.py: concurrent_audio_processor(task: ProcessingTask) -> ProcessingResult
    - Change: Ensure it returns a ProcessingResult (defined in app/realtime_queue) with correct field names; use _ensure_resolved to await/call any results from asr/mt/tts.
    - Ensure processing_time_ms is computed with at least 1 ms to satisfy tests.
  - app/realtime_queue.py: AsyncProcessingQueue.enqueue_task(self, task) -> bool
    - Change: keep current behavior but make sure no unexpected exceptions leak; ensure priority queue transfer is robust.
  - app/asr.py: transcribe_chunk(audio_bytes: bytes, language: Optional[str] = None) -> str
    - Change: Always return str; on failure return empty string and log.

- Removed functions
  - None.

[Classes]
Single sentence: Preserve existing classes but adjust a few fields / contracts and add small helpers where necessary.

Detailed breakdown:
- New classes
  - None required; prefer small helper functions and tests.

- Modified classes
  - StreamingPipelineCoordinator (app/pipeline_coordinator.py)
    - Ensure _pipeline_task_processor treats downstream result as ProcessingResult/PipelineResult and sets stage_latencies/total_latency_ms even when errors occur.
    - Guarantee get_next_result returns PipelineResult objects with stable fields.
  - StreamingASR (app/asr.py)
    - Minor internal changes to return types only; no change to public class name or constructor.
  - StreamingMT (app/mt.py)
    - No API changes; ensure error-handling leaves original text as fallback.
  - StreamingTTS (app/tts.py)
    - Ensure synthesize_text returns bytes synchronously (even if underlying implementation uses threads).
  - AsyncProcessingQueue (app/realtime_queue.py)
    - Ensure queue stats are consistent and is_queue_full uses the underlying asyncio.Queue.full() semantics.

- Removed classes
  - None.

[Dependencies]
Single sentence: No new third-party dependencies; adjust runtime config and keep existing packages.

Details:
- No new pip packages to add. Continue using:
  - faster-whisper (ASR), pyttsx3 or Coqui (TTS), httpx (MT client), soundfile, numpy, ffmpeg-backed conversion utilities already present in requirements.txt.
- Potential runtime configuration:
  - config.yaml: include m2m_service tuning keys (failure_threshold, circuit_open_duration, backoff_base, max_backoff, timeout_seconds).
- If the environment uses Coqui TTS optionally, mention how to enable in tuning guide; do not add runtime installs automatically.

[Testing]
Single sentence: Add focused unit tests to cover normalization helpers, backpressure trimming, and ProcessingResult shape; run full pytest suite and maintain Hypothesis coverage for new files.

Test file requirements and strategies:
- tests/test_ensure_resolved.py
  - Use pytest + pytest-asyncio and Hypothesis to generate combinations:
    - plain values (str, int), sync callables returning values, callables returning coroutines, nested callables, direct coroutines/awaitables.
    - ≥ 25 random combinations as required by repository .clinerules.
    - Assert final resolved value matches expected and that no exception is raised for nested depth <= 3.
- tests/test_backpressure_trimming.py
  - Create a StreamingAudioBuffer with small max_buffer_duration_ms, add chunks, call StreamingPipelineCoordinator.handle_backpressure() and assert total_duration_ms <= original & that recent chunk overlap remains.
  - Use deterministic chunk durations and explicit chunk IDs.
- tests/test_processing_result_shapes.py
  - Mock ASR/MT/TTS callables (sync and async variants) to validate concurrent_audio_processor returns ProcessingResult with:
    - task_id matching input
    - processing_time_ms >= 1
    - metadata contains "transcript" and "translation" when successful
    - error_message set on failure paths
  - Use both import-time dynamic imports and direct function references to verify _ensure_resolved behavior.
- Coverage goals:
  - At least 90% coverage on any new file added.
  - Existing tests should continue to run; fix test expectations where they were relying on previous inconsistent return shapes.

[Implementation Order]
Single sentence: Make small, reversible changes in an order that reduces risk: add normalization helpers and tests first, then fix WS/VAD/processor wiring, then harden ASR/MT/TTS behaviors, finally update docs and tuning scripts.

Numbered steps:
1. Add unit tests for normalization and backpressure (create tests/test_ensure_resolved.py, tests/test_backpressure_trimming.py, tests/test_processing_result_shapes.py). Run pytest to capture current baseline failures. (Reason: safety — tests codify desired behavior.)

2. Add or refine _ensure_resolved helper (app/ws.py) and write unit tests to validate behavior. (Reason: many tests patch functions to return coroutines/callables; helper reduces test flakiness.)

3. Update app/ws.py:
   - Standardize detect_speech_activity to return (has_speech, metadata) and remove any triple-unpack usages.
   - Wire duration_ms from metadata when calling coordinator.add_audio_chunk.
   - Ensure concurrent_audio_processor returns a ProcessingResult object (from app/realtime_queue) and uses _ensure_resolved to normalize ASR/MT/TTS returns.
   - Add defensive guards around stage calls (ASR -> return empty transcript; MT -> return original text on circuit open or failure; TTS -> return b"" on failure).
   - Run pytest and fix tests as they reveal mismatches.

4. Update app/realtime_queue.py and app/pipeline_coordinator.py if test expectations require minor field mapping (e.g., mapping ProcessingResult fields into PipelineResult). Ensure coordinator._pipeline_task_processor maps ProcessingResult -> PipelineResult and populates stage_latencies and total_latency_ms.

5. Harden app/asr.py, app/mt.py, app/tts.py:
   - ASR: ensure transcribe_chunk never returns coroutine and handles small/invalid audio safely.
   - MT: ensure translate_text returns a string in all cases and circuit breaker reads config.yaml.
   - TTS: ensure synthesize_text returns bytes synchronously even if implemented with threads; keep timeouts and cleanup.

6. Re-run full test suite, iterate on failing tests (likely small mapping or contract issues). Fix tests only if they depend on ambiguous behavior that was intentionally clarified.

7. Create docs/tuning_guide.md describing:
   - Which parameters to tune (PipelineConfig.chunk_size_ms, overlap_ms, max_buffer_duration_ms, queue_size, worker_count; MT backoff/circuit config).
   - How to use scripts/tune_parameters.py and interpret its output.
   - Example CLI commands to run tests and a local sample translation (no live audio required).
   - Guidance for Windows-specific TTS quirks and file locking.

8. Commit changes as a single PR with a clear change-log and run CI / full pytest locally. Request user to toggle to Act mode for code changes and test execution.

Notes, Constraints and Edge Cases:
- Preserve current project layout and API compatibility for external callers (FastAPI WebSocket routes); internal result shapes used by websocket_translate may be adjusted but must stay compatible with tests.
- Avoid adding heavy new dependencies to keep the repository easy to run locally.
- On Windows, pyttsx3 runAndWait may block; current thread-based timeout approach is retained. Document known issues and instructions for switching to Coqui TTS in tuning_guide.md.
- Tests may run differently under single-file pytest invocation due to sys.path differences. If a transient "No module named 'app'" occurs in filtered runs, document recommended pytest invocation (run from repo root: pytest -q) and ensure tests import app package via package-relative imports.
- Keep all code changes ≤ one module per ACT cycle if implementing code later (per .clinerules requirement).
