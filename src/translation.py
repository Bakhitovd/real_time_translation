import queue
import os
import openai
from asr import TRANSLATION_QUEUE

# Queue for sending translated English text to the TTS module
TTS_QUEUE = queue.Queue()

# Set your OpenAI API key (ensure you have a .env file or set it in your environment)
openai.api_key = os.getenv("OPENAI_API_KEY")

def translate_with_gpt4(russian_text):
    prompt = f"Translate the following text from Russian to English:\n\n{russian_text}"
    response = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=2000,
        temperature=0
    )
    english_text = response.choices[0].message["content"]
    return english_text.strip()

def translation_loop():
    """
    Reads Russian text from TRANSLATION_QUEUE, translates it using GPT-4,
    and pushes the English text into TTS_QUEUE.
    """
    while True:
        russian_text = TRANSLATION_QUEUE.get()
        if russian_text is None:
            break
        english_text = translate_with_gpt4(russian_text)
        print("Translated text:", english_text)
        TTS_QUEUE.put(english_text)
