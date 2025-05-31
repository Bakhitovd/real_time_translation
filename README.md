# Real-Time Speech Translation – Crawl Phase

This repository implements the **crawl** stage of an offline audio translation pipeline:  
1. **ASR** (speech → text) via local Whisper  
2. **MT** (text → text) via OpenAI GPT-4.1-mini  
3. **TTS** (text → speech) via Coqui TTS  

## System Requirements

- **OS:** Windows 11 (WSL2 optional for Linux tooling)  
- **Python:** ≥3.10  
- **GPU:** NVIDIA with CUDA 11.8 (highly recommended for Whisper & TTS acceleration)  

## Setup

1. Clone or pull this repository.  
2. Create and activate a Python virtual environment:  
   ```bash
   python -m venv venv
   .\\venv\\Scripts\\activate    # PowerShell or cmd
   ```
3. Install dependencies:  
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```
4. Set your OpenAI API key in an environment variable:  
   ```bash
   set OPENAI_API_KEY=sk-...
   ```
5. Verify CUDA support (optional):  
   ```python
   import torch
   print("CUDA available:", torch.cuda.is_available())
   ```

## Configuration

Review or adjust `config.yaml` to select:
- Whisper ASR model size (`tiny`, `base`, `small`, `medium`, `large`)
- OpenAI MT engine (default `gpt-4-1-mini`)
- Coqui TTS voice models for each language
- Logging level and other settings

## Usage

Translate an input file (e.g., Russian → English):

```bash
python scripts/translate.py \
  --input input_audio/ru_sample_01.mp3 \
  --source ru \
  --target en
```

Output audio will be written to `output_audio/ru_sample_01_en.wav`, and a log will be saved to `logs/ru_sample_01.log`

### Optional Flags

- `--model`: override Whisper model size  
- `--voice`: override Coqui TTS voice model  
- `--log-level`: override logging level (DEBUG, INFO, etc.)

## Folder Structure

```text
├─ input_audio/    # place your .wav or .mp3 files here
├─ output_audio/   # translated .wav outputs
├─ logs/           # per-file process logs
├─ scripts/
│   └─ translate.py
├─ config.yaml     # pipeline settings
├─ requirements.txt
└─ README.md
```

## Validation

After running, confirm:
- `output_audio/*.wav` exists and has non-zero duration  
- Corresponding `logs/*.log` contains `[✓] Whisper transcription`, `[✓] GPT translation`, `[✓] TTS synthesis`

## Additional Documentation
- Crawl phase summary: [docs/crawl_done.md](docs/crawl_done.md)
- Run phase definition of done: [docs/run_goal.md](docs/run_goal.md)
