#!/usr/bin/env python3
import os
import argparse
import wave
import pyaudio

def record_audio(duration, output_path, rate=16000, channels=1, chunk=1024):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    audio = pyaudio.PyAudio()
    stream = audio.open(format=pyaudio.paInt16,
                        channels=channels,
                        rate=rate,
                        input=True,
                        frames_per_buffer=chunk)
    print(f"Recording {duration}s of audio to {output_path}...")
    frames = []
    for _ in range(0, int(rate / chunk * duration)):
        data = stream.read(chunk)
        frames.append(data)
    print("Recording complete, saving file...")
    stream.stop_stream()
    stream.close()
    audio.terminate()

    wf = wave.open(output_path, 'wb')
    wf.setnchannels(channels)
    wf.setsampwidth(audio.get_sample_size(pyaudio.paInt16))
    wf.setframerate(rate)
    wf.writeframes(b''.join(frames))
    wf.close()
    print(f"File saved: {output_path}")

def main():
    parser = argparse.ArgumentParser(description="Record microphone input to .wav file")
    parser.add_argument("--duration", "-d", type=int, required=True,
                        help="Recording duration in seconds")
    parser.add_argument("--output", "-o", default="input_audio/record.wav",
                        help="Output WAV file path (default: input_audio/record.wav)")
    args = parser.parse_args()
    record_audio(args.duration, args.output)

if __name__ == "__main__":
    main()
