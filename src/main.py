import datetime
import numpy as np
import noisereduce as nr

from audio_input import audio_server, RATE
from asr import transcribe
from translation import translate_text
from tts import synthesize_tts
from mixer import mix_audio, save_mixed_audio

def main():
    print("Starting socket-based audio translation pipeline...")

    # Initialize accumulators for input and TTS audio
    input_accum = np.array([], dtype=np.float32)
    tts_accum = np.array([], dtype=np.float32)
    
    # Target accumulation duration in seconds (1 minute)
    target_duration = 20  
    target_samples = target_duration * RATE

    for i, audio_np in enumerate(audio_server()):
        print(f"\n--- Processing segment {i+1} ---")
        
        # Calculate and display RMS before noise reduction
        rms_before = np.sqrt(np.mean(audio_np ** 2))
        print(f"RMS before noise reduction: {rms_before:.4f}")
        
        # Apply noise reduction
        denoised_audio = nr.reduce_noise(y=audio_np, sr=RATE, stationary=False)
        rms_after = np.sqrt(np.mean(denoised_audio ** 2))
        print(f"RMS after noise reduction: {rms_after:.4f}")

        # Perform ASR (transcription)
        transcription = transcribe(denoised_audio)
        print("ASR transcription:", transcription)

        # Translate transcription from Russian to English
        translated_text = translate_text(transcription)
        print("Translated text:", translated_text)

        # Synthesize TTS audio from translated text
        tts_audio = synthesize_tts(translated_text)
        if tts_audio.size == 0:
            print("No TTS audio produced, skipping segment.")
            continue

        # Accumulate the denoised input and TTS audio
        input_accum = np.concatenate([input_accum, denoised_audio])
        tts_accum = np.concatenate([tts_accum, tts_audio])

        # Check if we've accumulated at least one minute of audio in both streams
        if len(input_accum) >= target_samples and len(tts_accum) >= target_samples:
            # Take only the first minute worth of samples
            input_segment = input_accum[:target_samples]
            tts_segment = tts_accum[:target_samples]

            # Mix the audio segments
            mixed_audio = mix_audio(input_segment, tts_segment)
            
            # Save the mixed audio with a timestamp
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"mixed_output_{timestamp}.wav"
            save_mixed_audio(mixed_audio, filename)
            print(f"Saved mixed audio to {filename}")

            # Remove the used samples from the accumulators
            input_accum = input_accum[target_samples:]
            tts_accum = tts_accum[target_samples:]

if __name__ == "__main__":
    main()