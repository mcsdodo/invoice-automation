"""Abstract base class for LLM clients."""

import json
import logging
import re
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class LLMClient(ABC):
    """Abstract LLM client defining the interface for all providers."""

    @abstractmethod
    async def generate_text(self, prompt: str) -> str | None:
        """Generate text from a prompt.

        Args:
            prompt: The prompt to send to the model.

        Returns:
            Generated text or None if an error occurred.
        """

    async def is_approval_email(self, email_body: str) -> tuple[bool, float]:
        """Classify if an email is an approval for a timesheet/invoice.

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
            logger.info("LLM unavailable for email classification, returning uncertain")
            return (False, 0.0)

        return self._parse_approval_response(response)

    async def is_invoice_pdf(
        self, text_content: str
    ) -> tuple[bool, str | None, float | None]:
        """Verify if text content from a PDF is an invoice.

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
            logger.info("LLM unavailable for invoice verification, returning uncertain")
            return (False, None, None)

        return self._parse_invoice_response(response)

    def _parse_approval_response(self, response: str) -> tuple[bool, float]:
        """Parse the LLM response for approval classification."""
        try:
            data = self._extract_json(response)

            is_approval = bool(data.get("is_approval", False))
            confidence = float(data.get("confidence", 0.0))
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
            return (False, 0.0)

    def _parse_invoice_response(
        self, response: str
    ) -> tuple[bool, str | None, float | None]:
        """Parse the LLM response for invoice verification."""
        try:
            data = self._extract_json(response)

            is_invoice = bool(data.get("is_invoice", False))
            invoice_number = data.get("invoice_number")
            total_amount = data.get("total_amount")

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
            return (False, None, None)

    @staticmethod
    def _extract_json(response: str) -> dict:
        """Extract JSON object from an LLM response, handling markdown code blocks."""
        json_text = response.strip()
        if json_text.startswith("```"):
            match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", json_text, re.DOTALL)
            if match:
                json_text = match.group(1)
        return json.loads(json_text)
