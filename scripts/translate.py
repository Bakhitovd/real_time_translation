#!/usr/bin/env python3
import os
import argparse
import logging
from faster_whisper import WhisperModel
import pyttsx3
import openai
import yaml
from dotenv import load_dotenv

def setup_logging(level):
    logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s",
                        level=getattr(logging, level))

def load_config(path="config.yaml"):
    with open(path, "r") as f:
        return yaml.safe_load(f)

def transcribe(audio_path, model_size):
    logging.info(f"Starting ASR on {audio_path} with Whisper '{model_size}'")
    model = WhisperModel(model_size, device="cpu")
    segments, info = model.transcribe(audio_path, language=None, task="transcribe")
    transcript = "".join([segment.text + " " for segment in segments]).strip()
    logging.info(f"ASR done. Duration: {info.duration:.1f}s")
    return transcript

def translate_text(text, source, target, mt_engine):
    prompt = f"Translate the following {source} text to {target}:\n\n{text}"
    logging.info(f"Translating text with OpenAI model '{mt_engine}'")
    response = openai.chat.completions.create(
        model=mt_engine,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    translated = response.choices[0].message.content.strip()
    logging.info("Translation complete")
    return translated

def synthesize(text, voice_model, target_lang, use_cuda, output_path):
    logging.info("Synthesizing speech with pyttsx3 offline TTS")
    engine = pyttsx3.init()
    engine.save_to_file(text, output_path)
    engine.runAndWait()
    logging.info(f"TTS output written to {output_path}")

def main():
    parser = argparse.ArgumentParser(description="Offline audio translation pipeline")
    parser.add_argument("--input", "-i", required=True,
                        help="Input audio file path (wav or mp3)")
    parser.add_argument("--source", "-s", required=True, choices=["en","ru"],
                        help="Source language code (en or ru)")
    parser.add_argument("--target", "-t", required=True, choices=["en","ru"],
                        help="Target language code (en or ru)")
    parser.add_argument("--model", help="Override Whisper model size")
    parser.add_argument("--voice", help="Override Coqui TTS voice model")
    parser.add_argument("--log-level", help="Override logging level")
    args = parser.parse_args()

    config = load_config()

    # Logging
    if args.log_level:
        config["logging"]["level"] = args.log_level
    setup_logging(config["logging"]["level"])

    # Load environment and API key
    load_dotenv()
    openai.api_key = os.getenv(config["openai_api_key_env"])
    if not openai.api_key:
        logging.error("OpenAI API key not set. Define it in environment variable " +
                      f"{config['openai_api_key_env']}")
        return

    # Prepare input/output paths
    audio_path = args.input
    basename = os.path.splitext(os.path.basename(audio_path))[0]
    output_dir = "output_audio"
    os.makedirs(output_dir, exist_ok=True)
    output_file = f"{basename}_{args.target}.wav"
    output_path = os.path.join(output_dir, output_file)

    # ASR
    asr_model = args.model or config["model"]["asr"]
    transcript = transcribe(audio_path, asr_model)

    # MT
    mt_engine = config["model"]["mt_engine"]
    translated_text = translate_text(transcript, args.source, args.target, mt_engine)

    # TTS
    voice_model = args.voice or config["model"]["voice_models"][args.target]
    use_cuda = config["coqui"]["use_cuda"]
    synthesize(translated_text, voice_model, args.target, use_cuda, output_path)

    # Logging summary
    os.makedirs("logs", exist_ok=True)
    log_path = os.path.join("logs", f"{basename}.log")
    with open(log_path, "w", encoding="utf-8") as logf:
        logf.write("[OK] Whisper transcription\n")
        logf.write("[OK] GPT translation\n")
        logf.write("[OK] TTS synthesis\n")
    logging.info(f"Log written to {log_path}")

if __name__ == "__main__":
    main()
