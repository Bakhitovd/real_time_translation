import torch
from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline

# Choose GPU if available, otherwise CPU.
device = "cuda:0" if torch.cuda.is_available() else "cpu"
torch_dtype = torch.float16 if torch.cuda.is_available() else torch.float32

model_id = "openai/whisper-large-v3-turbo"
print(f"Loading model '{model_id}' on {device} with dtype {torch_dtype}...")

# Load the model using safetensors for faster loading (if available)
model = AutoModelForSpeechSeq2Seq.from_pretrained(
    model_id,
    torch_dtype=torch_dtype,
    low_cpu_mem_usage=True,
    use_safetensors=True,
)
model.to(device)

# Load the processor (handles feature extraction and tokenization)
processor = AutoProcessor.from_pretrained(model_id)

# Create an ASR pipeline using the GPU (if available)
asr_pipeline = pipeline(
    "automatic-speech-recognition",
    model=model,
    tokenizer=processor.tokenizer,
    feature_extractor=processor.feature_extractor,
    torch_dtype=torch_dtype,
    device=0 if torch.cuda.is_available() else -1,
)

# Path to your local audio file (update the path as needed)
audio_path = "speech_ru.mp3"

# Perform transcription
result = asr_pipeline(audio_path, return_timestamps=True)
print("Transcription:", result["text"])
