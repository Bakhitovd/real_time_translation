"""
Test script for Machine Translation (MT) using OpenAI API.
Usage:
    python scripts/test_mt.py "Text to translate" --source en --target ru
"""

import sys
import os
import asyncio

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.mt import translate_text

def usage():
    print("Usage: python scripts/test_mt.py \"Text to translate\" --source en --target ru")
    print("Example: python scripts/test_mt.py \"Hello world\" --source en --target ru")
    sys.exit(1)

async def main():
    if len(sys.argv) < 6:
        usage()

    text = sys.argv[1]
    source_lang = None
    target_lang = None

    # Parse arguments
    for i in range(2, len(sys.argv), 2):
        if i + 1 < len(sys.argv):
            if sys.argv[i] == "--source":
                source_lang = sys.argv[i+1]
            elif sys.argv[i] == "--target":
                target_lang = sys.argv[i+1]

    if not source_lang or not target_lang:
        usage()

    print(f"Translating: '{text}'")
    print(f"From: {source_lang} → To: {target_lang}")
    print("Processing...")
    
    try:
        translated = await translate_text(text, source_lang, target_lang)
        print(f"\nTranslation: '{translated}'")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
