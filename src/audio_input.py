import socket
import numpy as np

# === Audio Configuration ===
RATE = 16000            # Sampling rate (Hz)
CHUNK = 1024            # Number of bytes per socket recv
BUFFER_DURATION = 3     # seconds per segment
BYTES_PER_SAMPLE = 2    # 16-bit audio
BUFFER_SIZE = RATE * BUFFER_DURATION * BYTES_PER_SAMPLE

# TCP server settings
HOST = ''      # Listen on all interfaces
PORT = 50007   # TCP port

def audio_server():
    """
    Starts a TCP server that yields audio segments (as numpy arrays) when enough data is received.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((HOST, PORT))
    s.listen(1)
    print(f"Audio server listening on port {PORT}...")
    conn, addr = s.accept()
    print("Connected by", addr)
    audio_buffer = bytearray()
    try:
        while True:
            data = conn.recv(CHUNK)
            if not data:
                break
            audio_buffer.extend(data)
            if len(audio_buffer) >= BUFFER_SIZE:
                segment = audio_buffer[:BUFFER_SIZE]
                audio_buffer = audio_buffer[BUFFER_SIZE:]
                # Convert raw PCM bytes to a normalized numpy array (float32 in [-1, 1])
                audio_np = np.frombuffer(segment, dtype=np.int16).astype(np.float32) / 32768.0
                yield audio_np
    except KeyboardInterrupt:
        print("Audio server interrupted. Shutting down...")
    finally:
        conn.close()
        s.close()
