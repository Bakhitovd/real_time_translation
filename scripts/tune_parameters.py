#!/usr/bin/env python3
"""
Tuning helper for real_time_trans pipeline.

Usage:
  - Place representative audio files in input_audio/ (wav or mp3)
  - Run: python scripts/tune_parameters.py --files input_audio/*.wav
  - The script will run each file through the pipeline components (conversion -> VAD -> buffer -> ASR -> MT -> TTS)
    in a synthetic single-session coordinator and measure per-stage latencies and overall E2E time.
  - It prints CSV-like output and a short recommendations summary.

Notes:
  - This script is non-destructive and only uses existing public APIs from app/.
  - It requires the process to have the same environment as the server (models installed, ffmpeg available, etc).
  - Use --dry-run to run components in "validate-only" mode (no TTS or heavy model runs).
"""

import argparse
import glob
import io
import logging
import time
import traceback
from pathlib import Path

from app.utils import convert_audio_to_wav, get_audio_info, validate_wav_format
from app.ws import detect_speech_activity
from app.asr import get_asr_instance, transcribe_chunk
from app.mt import get_mt_instance, translate_text
from app.tts import get_tts_instance, synthesize_text
from app.pipeline_coordinator import create_realtime_config, create_pipeline_coordinator

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def run_single_file(path: Path, dry_run: bool):
    result = {
        "file": str(path),
        "size_bytes": path.stat().st_size,
        "conv_ms": None,
        "vad_ms": None,
        "asr_ms": None,
        "mt_ms": None,
        "tts_ms": None,
        "e2e_ms": None,
        "success": False,
        "error": ""
    }

    try:
        t0 = time.time()

        audio_bytes = path.read_bytes()

        # Convert (no-op if already WAV)
        t = time.time()
        wav = convert_audio_to_wav(audio_bytes, input_format=path.suffix.lstrip("."))
        result["conv_ms"] = int((time.time() - t) * 1000)

        # VAD
        t = time.time()
        has_speech, vad_meta = detect_speech_activity(wav)
        result["vad_ms"] = int((time.time() - t) * 1000)

        # ASR
        t = time.time()
        asr_text = transcribe_chunk(wav, language=None)
        result["asr_ms"] = int((time.time() - t) * 1000)

        # MT
        t = time.time()
        mt_text = ""
        if not dry_run:
            # call translate_text helper which uses global MT instance
            mt_text = translate_text(asr_text, "auto", "en")
            if hasattr(mt_text, "__await__"):
                # in case it's a coroutine
                import asyncio
                mt_text = asyncio.get_event_loop().run_until_complete(mt_text)
        result["mt_ms"] = int((time.time() - t) * 1000)

        # TTS
        t = time.time()
        if not dry_run:
            tts_audio = synthesize_text(mt_text or asr_text)
        else:
            tts_audio = b""
        result["tts_ms"] = int((time.time() - t) * 1000)

        result["e2e_ms"] = int((time.time() - t0) * 1000)
        result["success"] = True
        return result

    except Exception as e:
        logging.error(f"Error processing {path}: {e}\n{traceback.format_exc()}")
        result["error"] = str(e)
        return result


def recommend_params(results):
    """
    Simple heuristics to recommend tuning parameters based on observed latencies.
    - If avg asr_ms >> target, suggest smaller chunk_size_ms or larger worker_count (if CPU bound).
    - If queue overflows observed (not measured here), suggest larger queue_size or slower input rate.
    """
    asr_times = [r["asr_ms"] for r in results if r["asr_ms"] is not None and r["success"]]
    mt_times = [r["mt_ms"] for r in results if r["mt_ms"] is not None and r["success"]]
    tts_times = [r["tts_ms"] for r in results if r["tts_ms"] is not None and r["success"]]

    avg_asr = sum(asr_times) / len(asr_times) if asr_times else 0
    avg_mt = sum(mt_times) / len(mt_times) if mt_times else 0
    avg_tts = sum(tts_times) / len(tts_times) if tts_times else 0
    total = avg_asr + avg_mt + avg_tts

    recs = []
    recs.append(f"Avg ASR: {avg_asr:.0f} ms; Avg MT: {avg_mt:.0f} ms; Avg TTS: {avg_tts:.0f} ms; Sum: {total:.0f} ms")

    # Chunk size recommendation
    if avg_asr > 1200:
        recs.append("- ASR is slow. Consider increasing model size? or reduce chunk_size_ms to smaller (e.g., 400-600ms) to reduce per-segment processing.")
    elif avg_asr > 600:
        recs.append("- ASR moderate. Consider chunk_size_ms ~600ms and worker_count 2-4.")
    else:
        recs.append("- ASR fast: chunk_size_ms 600-800ms is reasonable.")

    # MT/tTS recommendations
    if avg_mt > 1000:
        recs.append("- MT is slow: increase MT service resources or increase MT timeout/retries and consider batching translations.")
    if avg_tts > 800:
        recs.append("- TTS is slow: consider GPU-enabled TTS (Coqui) or prewarming TTS engine.")

    # Overall latency guidance
    if total < 1800:
        recs.append("- System appears capable of sub-2s E2E on these samples.")
    else:
        recs.append("- E2E is >2s. Try reducing chunk size, enabling more workers, or offloading heavy models to GPU.")

    return recs


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--files", nargs="+", help="Input audio files (globs supported)", required=True)
    p.add_argument("--dry-run", action="store_true", help="Do not run MT/TTS (faster local checks)")
    args = p.parse_args()

    files = []
    for pattern in args.files:
        files += glob.glob(pattern)
    files = sorted(set(files))
    if not files:
        print("No files matched")
        return

    results = []
    for f in files:
        print(f"Processing {f} ...")
        res = run_single_file(Path(f), dry_run=args.dry_run)
        print(res)
        results.append(res)

    print("\nRecommendations:")
    for line in recommend_params(results):
        print(line)


if __name__ == "__main__":
    main()
