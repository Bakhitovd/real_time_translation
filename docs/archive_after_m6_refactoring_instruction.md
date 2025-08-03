Here’s a **precise, technical instruction set for your devLead** to replace the current MT component (OpenAI/DeepL API) with a **self-hosted, context-aware, near-DeepL-quality solution using Meta’s M2M-100 (418M) model**.
This conversion will yield sub-200ms translation latency per chunk and up to 1k token context (multi-sentence, not sentence-by-sentence), and is targeted for **efficient, production-grade integration** with your concurrent, real-time pipeline.

---

# M2M-100 418M Integration – Development Task Brief

## Objective

**Replace the current MT implementation** (OpenAI API) in the real-time speech translation pipeline with a **self-hosted, streaming M2M-100 (418M) RU→EN model** to achieve:

* Near-DeepL translation quality, context-aware output (1k tokens context window)
* <200ms latency per 30-token segment on local RTX A4000
* Fully on-premise, no external API dependency
* Maintain pipeline concurrency and sub-2s E2E latency

---

## Task Breakdown

### 1. Environment and Model Preparation

* **a. Acquire model**

  * Pull M2M-100 (418M) from HuggingFace:

    ```
    transformers-cli login  # if needed
    git lfs install
    git clone https://huggingface.co/facebook/m2m100_418M
    ```
* **b. Dependencies**

  * Add/verify in `requirements.txt`:

    ```
    transformers==4.41.2   # or most recent stable
    torch                  # CUDA build for your card
    fairseq-streaming      # For streaming, context-aware inference
    fastapi, uvicorn       # For API server if you want to isolate the MT service
    ```
  * Install/update with pip as needed.

---

### 2. MT Microservice (Recommended: FastAPI or Flask)

* **a. Build a minimal translation microservice**

  * Endpoint: `POST /translate`

    * Input: JSON with `src_text` (Russian text chunk) and `context` (previous 1–2 sentences, optional)
    * Output: Translated English text (same chunk size)
  * Load M2M-100 with tokenizer; warm up on startup.
  * **Context:** Maintain a buffer of up to 1k tokens (concatenate last 2–3 sentences as prompt before current chunk).
  * Use batching if requests are frequent (for GPU efficiency).
  * Log inference time and throughput for each request.

* **b. Example server code (simplified)**

  ```python
  from fastapi import FastAPI, Request
  from transformers import M2M100ForConditionalGeneration, M2M100Tokenizer
  import torch

  app = FastAPI()
  tokenizer = M2M100Tokenizer.from_pretrained('facebook/m2m100_418M')
  model = M2M100ForConditionalGeneration.from_pretrained('facebook/m2m100_418M').cuda()
  model.eval()

  @app.post("/translate")
  async def translate(req: Request):
      data = await req.json()
      src = data['src_text']
      ctx = data.get('context', '')
      full_input = ctx + " " + src if ctx else src
      batch = tokenizer(full_input, return_tensors="pt", padding=True).to("cuda")
      with torch.no_grad():
          out = model.generate(**batch, forced_bos_token_id=tokenizer.get_lang_id("en"), max_new_tokens=80)
      translation = tokenizer.batch_decode(out, skip_special_tokens=True)[0]
      return {"translation": translation}
  ```

  *(Adapt as needed for production, e.g. batching, error handling, metrics)*

---

### 3. **Pipeline Integration**

* **a. Replace current `app/mt.py` logic**

  * Remove OpenAI API logic; substitute with async HTTP client calls to the new local MT service.
  * Maintain the same async/concurrent handling pattern as the rest of the pipeline (use `httpx` or `aiohttp` for async requests).
  * **Context feeding:** Before sending a new chunk, fetch/concatenate up to 2 previous source sentences from buffer for better context.
  * Tune chunk size to \~30 tokens for optimal latency/quality balance (do NOT send sentence-by-sentence if you want context).

* **b. Error handling / fallback**

  * If MT service fails or GPU is at capacity, gracefully degrade (e.g. fall back to sentence-by-sentence, or return placeholder).

---

### 4. **Performance and Monitoring**

* **a. Add translation timing (start, end, duration) to `LatencyMonitor`**

  * Integrate with your `latency_monitor.py`, so the MT chunk timing is tracked and visible in dashboards.
* **b. GPU Utilization**

  * Optionally, add GPU monitoring (e.g. `nvidia-smi` polling) to abort/failover if utilization exceeds threshold.

---

### 5. **Deployment and Scaling**

* **a. Run MT microservice as Docker container (if desired)**

  * Write `Dockerfile` (CUDA base, copy in model, expose port).
  * Document GPU requirement in deployment guide (16GB card per 4–5 concurrent streams).

* **b. Update CI/CD**

  * Add automated tests for translation accuracy and latency using real Russian audio samples.
  * Add health check endpoint for load balancer integration.

---

### 6. **Documentation and Handoff**

* Update architecture docs (`/docs/`):

  * Replace “MT: OpenAI API” with “MT: M2M-100 microservice”
  * List new environment variables, GPU requirements, and test coverage status.
* Provide migration instructions for any rollback (switching back to API).

---

## Key Requirements

* **Latency:** <200ms per 30-token chunk (must pass in 90%+ of real-world cases, validate with `latency_monitor.py`)
* **Context:** Buffer last 2–3 sentences for each chunk to maximize translation coherence
* **Reliability:** Fail gracefully on OOM or service error, never block pipeline
* **Production**: Must pass current 90%+ test coverage, integrate with all performance and error-monitoring infra

---

## Reference Links

* [HuggingFace M2M-100 418M](https://huggingface.co/facebook/m2m100_418M)
* [Meta M2M-100 research paper](https://arxiv.org/abs/2010.11125)
* [Example FastAPI + transformers](https://huggingface.co/docs/transformers/main/en/serialization#serving-models-with-fastapi)
* [fairseq streaming codebase](https://github.com/pytorch/fairseq/tree/main/examples/simultaneous_translation)
* [CUDA Docker base image](https://hub.docker.com/r/nvidia/cuda)

---

**Summary:**
Your devLead must build a GPU-backed local microservice running M2M-100 (418M) with 1k token context, replace API-based MT with async local calls, buffer context per session, and ensure all latency/monitoring hooks remain intact. Document and test thoroughly.
**Goal:** Retain your current pipeline’s concurrency and performance, but remove the API cost and deliver context-aware, near-DeepL-quality RU→EN translation—entirely on-prem, fully integrated.

If you want the full implementation plan as a checklist or need example code snippets for any integration point, just say so.
