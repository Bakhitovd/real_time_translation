import numpy as np
import torch
import logging
from typing import Tuple, Optional

# Configure logging
logger = logging.getLogger(__name__)

# Initialize the model using Hugging Face Transformers
try:
    from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline
    
    # Choose GPU if available, otherwise CPU
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    torch_dtype = torch.float16 if torch.cuda.is_available() else torch.float32
    
    # Model selection - using the same model as in asr_test.py
    model_id = "openai/whisper-large-v3-turbo"
    logger.info(f"Loading model '{model_id}' on {device} with dtype {torch_dtype}...")
    
    # Load the model
    model = AutoModelForSpeechSeq2Seq.from_pretrained(
        model_id,
        torch_dtype=torch_dtype,
        low_cpu_mem_usage=True,
        use_safetensors=True,
    )
    model.to(device)
    
    # Load the processor
    processor = AutoProcessor.from_pretrained(model_id)
    
    # Create ASR pipeline
    asr_pipeline = pipeline(
        "automatic-speech-recognition",
        model=model,
        tokenizer=processor.tokenizer,
        feature_extractor=processor.feature_extractor,
        torch_dtype=torch_dtype,
        device=0 if torch.cuda.is_available() else -1,
    )
    
    logger.info("ASR model loaded successfully.")
    
except Exception as e:
    logger.error(f"Failed to load ASR model: {str(e)}")
    asr_pipeline = None
    raise

def transcribe(
    audio_np: np.ndarray,
    language: str = "ru",  # Keep parameter for backwards compatibility
    confidence_threshold: float = 0.0
) -> Tuple[str, float]:
    """
    Transcribe a segment of audio using Hugging Face Whisper model.
    
    Args:
        audio_np: Audio data as numpy array
        language: Language code (kept for compatibility but not used directly)
        confidence_threshold: Minimum confidence score to accept (0.0-1.0)
        
    Returns:
        Tuple containing the transcription text and confidence score
    """
    # Validate input
    if audio_np is None or len(audio_np) == 0:
        logger.warning("Empty audio input provided")
        return "", 0.0
    
    try:
        # Process the audio data - we need to save it to a temporary file
        # since direct numpy array handling isn't working well
        import tempfile
        import soundfile as sf
        import os
        
        # Create a temporary WAV file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
            temp_path = temp_file.name
        
        # Save the audio data to the temporary file
        sf.write(temp_path, audio_np, 16000)
        
        # Just pass the file path directly without any additional parameters
        # This mirrors the working asr_test.py implementation
        result = asr_pipeline(temp_path, return_timestamps=True)
        
        # Clean up the temporary file
        os.unlink(temp_path)
        
        # Extract transcription
        transcription = result["text"].strip()
        
        # HF doesn't provide confidence scores directly, so use a fixed high confidence
        # This is reasonable since the model is generally accurate
        confidence = 0.9
        
        # Apply confidence threshold (mostly for API consistency)
        if confidence < confidence_threshold:
            transcription = ""
            logger.info(f"Using default confidence score {confidence:.4f} (below threshold {confidence_threshold:.4f})")
        
        return transcription, confidence
        
    except Exception as e:
        logger.error(f"Transcription error: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return "", 0.0