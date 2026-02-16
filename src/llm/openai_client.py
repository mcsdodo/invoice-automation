"""OpenAI-compatible LLM client (works with Ollama, OpenAI, etc.)."""

import logging

from openai import AsyncOpenAI

from src.config import settings
from src.llm.base import LLMClient

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30.0


class OpenAIClient(LLMClient):
    """Async client using the OpenAI API (compatible with Ollama)."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        self.model_name = model or settings.llm_model
        self._client = AsyncOpenAI(
            base_url=base_url or settings.llm_base_url,
            api_key=api_key or settings.llm_api_key,
            timeout=timeout,
        )

    async def generate_text(self, prompt: str) -> str | None:
        """Generate text from a prompt."""
        try:
            response = await self._client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.warning("OpenAI-compatible API error: %s", str(e))
            return None
