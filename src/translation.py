import os
import openai
import json
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get the API key
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("OPENAI_API_KEY environment variable not set. Please set it in your .env file.")

client = openai.OpenAI(api_key=api_key)
# Global conversation context for translation.
translation_context = [
    {
        "role": "system",
        "content": (
            "You are a professional translator. "
            "Translate the following Russian text into English. "
            "Return only a valid JSON object with exactly one key: 'translation', "
            "whose value is the translated text. Do not include any extra text or keys. "
            "Use any previous conversation context to maintain consistency."
        )
    }
]

def translate_text(russian_text: str, debug: bool = False) -> str:
    """
    Translate the given Russian text to English using OpenAI's Chat Completion API
    with structured output. Maintains context between calls for consistency.

    Args:
        russian_text: The Russian text to translate
        debug: Whether to print debug information (including raw JSON)

    Returns:
        The translated English text, or an empty string if no text was provided.
    """
    global translation_context

    # Check if the incoming text is nonempty
    if not russian_text.strip():
        return ""

    # Append the new transcription as a user message
    translation_context.append({"role": "user", "content": russian_text})

    try:
        # Call the Chat Completion API with a structured output format
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=translation_context,
            temperature=0,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "trans_response",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "translation": {
                                "type": "string",
                                "description": "The translated text."
                            }
                        },
                        "required": ["translation"],
                        "additionalProperties": False
                    }
                }
            }
        )

        # Print the raw JSON string returned if debug is enabled
        if debug:
            print(response.choices[0].message.content)

        # Use json.loads() to parse the JSON string
        translation_obj = json.loads(response.choices[0].message.content)
        translated_text = translation_obj["translation"]

        # Append the assistant's translation to the context for future calls
        translation_context.append({"role": "assistant", "content": translated_text})

        return translated_text

    except Exception as e:
        print(f"Translation error: {str(e)}")
        return f"[Translation error: {str(e)}]"
