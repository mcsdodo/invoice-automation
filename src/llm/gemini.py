"""Gemini LLM client for email classification and invoice verification."""

import asyncio
import logging
import re
from typing import Any

import google.generativeai as genai
from google.generativeai.types import GenerateContentResponse

from src.config import settings

logger = logging.getLogger(__name__)

# Default timeout for API calls (30 seconds)
DEFAULT_TIMEOUT = 30.0


class GeminiClient:
    """Async client for Gemini LLM API."""

    def __init__(self, api_key: str | None = None, timeout: float = DEFAULT_TIMEOUT):
        """Initialize the Gemini client.

        Args:
            api_key: Gemini API key. If not provided, uses settings.gemini_api_key.
            timeout: Timeout for API calls in seconds. Defaults to 30s.
        """
        self.api_key = api_key or settings.gemini_api_key
        self.timeout = timeout
        self._model: genai.GenerativeModel | None = None

        # Configure the API
        genai.configure(api_key=self.api_key)

    @property
    def model(self) -> genai.GenerativeModel:
        """Get or create the generative model (lazy initialization)."""
        if self._model is None:
            self._model = genai.GenerativeModel("gemini-2.0-flash-lite")
        return self._model

    async def generate_text(self, prompt: str) -> str | None:
        """Generate text from a prompt.

        Args:
            prompt: The prompt to send to the model.

        Returns:
            Generated text or None if an error occurred.
        """
        try:
            # Run the synchronous API call in a thread pool with timeout
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

    async def is_approval_email(self, email_body: str) -> tuple[bool, float]:
        """Classify if an email is an approval for a timesheet/invoice.

        Uses LLM to analyze the email content and determine if it represents
        an approval. Returns uncertain result (False, 0.0) on API errors
        so the caller can escalate to Telegram for manual classification.

        Args:
            email_body: The email body text to analyze.

        Returns:
            Tuple of (is_approval, confidence) where:
            - is_approval: True if the email appears to be an approval
            - confidence: Float 0-1 indicating confidence level
            Returns (False, 0.0) on API errors (uncertain result).
        """
        prompt = f"""Analyze the following email and determine if it is approving a timesheet or invoice submission.

Email content:
---
{email_body}
---

Answer with a JSON object in this exact format:
{{"is_approval": true/false, "confidence": 0.0-1.0, "reason": "brief explanation"}}

Consider these as approval indicators:
- Words like "approved", "accepted", "ok", "agreed", "confirmed"
- Slovak words like "schvalene", "schvalujem", "suhlasim", "v poriadku"
- Positive acknowledgment of timesheet/invoice receipt

Consider these as non-approval indicators:
- Questions or requests for changes
- Rejections or denials
- Unrelated emails

Respond ONLY with the JSON object, no other text."""

        response = await self.generate_text(prompt)

        if response is None:
            # API error - return uncertain result
            logger.info("LLM unavailable for email classification, returning uncertain")
            return (False, 0.0)

        # Parse the response
        return self._parse_approval_response(response)

    def _parse_approval_response(self, response: str) -> tuple[bool, float]:
        """Parse the LLM response for approval classification.

        Args:
            response: The raw LLM response text.

        Returns:
            Tuple of (is_approval, confidence).
        """
        try:
            # Try to extract JSON from the response
            # Handle potential markdown code blocks
            json_text = response.strip()
            if json_text.startswith("```"):
                # Extract content between code blocks
                match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", json_text, re.DOTALL)
                if match:
                    json_text = match.group(1)

            # Parse JSON
            import json
            data = json.loads(json_text)

            is_approval = bool(data.get("is_approval", False))
            confidence = float(data.get("confidence", 0.0))

            # Clamp confidence to valid range
            confidence = max(0.0, min(1.0, confidence))

            logger.debug(
                "Email classification: is_approval=%s, confidence=%.2f, reason=%s",
                is_approval,
                confidence,
                data.get("reason", "N/A"),
            )

            return (is_approval, confidence)

        except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
            logger.warning("Failed to parse LLM approval response: %s", str(e))
            # Return uncertain on parse errors
            return (False, 0.0)

    async def is_invoice_pdf(
        self, text_content: str
    ) -> tuple[bool, str | None, float | None]:
        """Verify if text content from a PDF is an invoice.

        Uses LLM to analyze extracted PDF text and determine if it's an invoice.
        Returns uncertain result on API errors so the caller can escalate
        to Telegram for manual verification.

        Args:
            text_content: Text extracted from the PDF.

        Returns:
            Tuple of (is_invoice, invoice_number, total_amount) where:
            - is_invoice: True if the PDF appears to be an invoice
            - invoice_number: Extracted invoice number or None
            - total_amount: Extracted total amount or None
            Returns (False, None, None) on API errors (uncertain result).
        """
        prompt = f"""Analyze the following text extracted from a PDF and determine if it is an invoice.

PDF text content:
---
{text_content[:4000]}
---

Answer with a JSON object in this exact format:
{{"is_invoice": true/false, "invoice_number": "string or null", "total_amount": number_or_null, "currency": "string or null", "confidence": 0.0-1.0, "reason": "brief explanation"}}

Look for these invoice indicators:
- Invoice number or "Faktura" / "Invoice" header
- Line items with prices
- Total amount due
- Business/company information
- Date and payment terms

If you cannot find specific fields, use null for those values.
Respond ONLY with the JSON object, no other text."""

        response = await self.generate_text(prompt)

        if response is None:
            # API error - return uncertain result
            logger.info("LLM unavailable for invoice verification, returning uncertain")
            return (False, None, None)

        # Parse the response
        return self._parse_invoice_response(response)

    def _parse_invoice_response(
        self, response: str
    ) -> tuple[bool, str | None, float | None]:
        """Parse the LLM response for invoice verification.

        Args:
            response: The raw LLM response text.

        Returns:
            Tuple of (is_invoice, invoice_number, total_amount).
        """
        try:
            # Try to extract JSON from the response
            json_text = response.strip()
            if json_text.startswith("```"):
                match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", json_text, re.DOTALL)
                if match:
                    json_text = match.group(1)

            import json
            data = json.loads(json_text)

            is_invoice = bool(data.get("is_invoice", False))
            invoice_number = data.get("invoice_number")
            total_amount = data.get("total_amount")

            # Ensure types are correct
            if invoice_number is not None:
                invoice_number = str(invoice_number)

            if total_amount is not None:
                try:
                    total_amount = float(total_amount)
                except (ValueError, TypeError):
                    total_amount = None

            logger.debug(
                "Invoice verification: is_invoice=%s, number=%s, amount=%s, reason=%s",
                is_invoice,
                invoice_number,
                total_amount,
                data.get("reason", "N/A"),
            )

            return (is_invoice, invoice_number, total_amount)

        except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
            logger.warning("Failed to parse LLM invoice response: %s", str(e))
            # Return uncertain on parse errors
            return (False, None, None)


# Convenience functions using a shared client instance
_default_client: GeminiClient | None = None


def get_client() -> GeminiClient:
    """Get or create the default Gemini client."""
    global _default_client
    if _default_client is None:
        _default_client = GeminiClient()
    return _default_client


async def is_approval_email(email_body: str) -> tuple[bool, float]:
    """Convenience function to classify an approval email.

    Args:
        email_body: The email body text to analyze.

    Returns:
        Tuple of (is_approval, confidence).
    """
    return await get_client().is_approval_email(email_body)


async def is_invoice_pdf(text_content: str) -> tuple[bool, str | None, float | None]:
    """Convenience function to verify an invoice PDF.

    Args:
        text_content: Text extracted from the PDF.

    Returns:
        Tuple of (is_invoice, invoice_number, total_amount).
    """
    return await get_client().is_invoice_pdf(text_content)
