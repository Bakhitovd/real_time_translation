import requests

payload = {
    "session_id": "test",
    "text": "Привет, мир!",
    "source_lang": "ru",
    "target_lang": "en",
    "use_context": True
}

resp = requests.post("http://localhost:8001/translate", json=payload)
print(resp.json())