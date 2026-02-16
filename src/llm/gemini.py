"""Gemini LLM client for email classification and invoice verification."""

import asyncio
import logging

import google.generativeai as genai
from google.generativeai.types import GenerateContentResponse

from src.config import settings
from src.llm.base import LLMClient

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30.0


class GeminiClient(LLMClient):
    """Async client for Gemini LLM API."""

    def __init__(self, api_key: str | None = None, timeout: float = DEFAULT_TIMEOUT):
        self.api_key = api_key or settings.gemini_api_key
        self.timeout = timeout
        self._model: genai.GenerativeModel | None = None
        genai.configure(api_key=self.api_key)

    @property
    def model(self) -> genai.GenerativeModel:
        """Get or create the generative model (lazy initialization)."""
        if self._model is None:
            self._model = genai.GenerativeModel(settings.llm_model)
        return self._model

    async def generate_text(self, prompt: str) -> str | None:
        """Generate text from a prompt."""
        try:
            loop = asyncio.get_event_loop()
            response: GenerateContentResponse = await asyncio.wait_for(
                loop.run_in_executor(None, self.model.generate_content, prompt),
                timeout=self.timeout,
            )
            return response.text
        except asyncio.TimeoutError:
            logger.warning("Gemini API timeout after %.1f seconds", self.timeout)
            return None
        except Exception as e:
            logger.warning("Gemini API error: %s", str(e))
            return None
