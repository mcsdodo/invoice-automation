"""LLM integration module with provider strategy pattern."""

from src.llm.base import LLMClient


def create_llm_client() -> LLMClient:
    """Create an LLM client based on configuration.

    Uses LLM_PROVIDER env var to select the provider:
    - "gemini": Google Gemini API (default)
    - "openai": OpenAI-compatible API (Ollama, OpenAI, etc.)
    """
    from src.config import settings

    if settings.llm_provider == "openai":
        from src.llm.openai_client import OpenAIClient
        return OpenAIClient()
    else:
        from src.llm.gemini import GeminiClient
        return GeminiClient()


__all__ = [
    "LLMClient",
    "create_llm_client",
]
