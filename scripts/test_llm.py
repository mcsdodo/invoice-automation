"""Quick test for LLM API credentials (any configured provider)."""
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from src.config import settings
from src.llm import create_llm_client


async def main():
    print(f"Provider: {settings.llm_provider}")
    print(f"Model:    {settings.llm_model}")
    if settings.llm_provider == "openai":
        print(f"Base URL: {settings.llm_base_url}")

    client = create_llm_client()
    response = await client.generate_text("Say 'Hello from LLM!' in exactly 5 words.")

    if response:
        print(f"Response: {response.strip()}")
    else:
        print("ERROR: No response from LLM")
        exit(1)


asyncio.run(main())
