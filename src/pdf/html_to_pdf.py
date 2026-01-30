"""HTML to PDF converter using Playwright."""

import asyncio
import logging
from pathlib import Path
from typing import Self

from playwright.async_api import Browser, async_playwright, Playwright

logger = logging.getLogger(__name__)

# Default timeout for PDF conversion (30 seconds)
DEFAULT_TIMEOUT_MS = 30000


class HtmlToPdfError(Exception):
    """Error raised when HTML to PDF conversion fails."""

    pass


class HtmlToPdfConverter:
    """
    Converts HTML content to PDF using Playwright (headless Chromium).

    Features:
    - Lazy browser initialization (starts on first use)
    - Reuses browser instance across conversions
    - Configurable timeout
    - Graceful shutdown

    Usage:
        async with HtmlToPdfConverter() as converter:
            await converter.convert("<html>...</html>", output_path)

    Or manually:
        converter = HtmlToPdfConverter()
        await converter.convert(html, output_path)
        await converter.close()
    """

    def __init__(self, timeout_ms: int = DEFAULT_TIMEOUT_MS):
        """
        Initialize the converter.

        Args:
            timeout_ms: Timeout in milliseconds for PDF generation.
        """
        self._timeout_ms = timeout_ms
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._lock = asyncio.Lock()

    async def __aenter__(self) -> Self:
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit - closes browser."""
        await self.close()

    async def _ensure_browser(self) -> Browser:
        """
        Ensure browser is initialized, starting it if needed.

        Thread-safe via asyncio lock.
        """
        if self._browser is not None:
            return self._browser

        async with self._lock:
            # Double-check after acquiring lock
            if self._browser is not None:
                return self._browser

            logger.debug("Starting Playwright browser...")
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=True,
            )
            logger.info("Playwright browser started")
            return self._browser

    async def convert(
        self,
        html: str,
        output_path: Path | str,
        *,
        timeout_ms: int | None = None,
    ) -> Path:
        """
        Convert HTML string to PDF file.

        Args:
            html: HTML content to convert.
            output_path: Path for the output PDF file.
            timeout_ms: Optional timeout override in milliseconds.

        Returns:
            Path to the generated PDF file.

        Raises:
            HtmlToPdfError: If conversion fails or times out.
        """
        output_path = Path(output_path)
        timeout = timeout_ms if timeout_ms is not None else self._timeout_ms

        try:
            browser = await self._ensure_browser()

            # Create a new page for this conversion
            page = await browser.new_page()

            try:
                # Set content with timeout
                await page.set_content(html, timeout=timeout, wait_until="networkidle")

                # Ensure output directory exists
                output_path.parent.mkdir(parents=True, exist_ok=True)

                # Generate PDF
                await page.pdf(
                    path=str(output_path),
                    format="A4",
                    print_background=True,
                    margin={
                        "top": "20mm",
                        "bottom": "20mm",
                        "left": "15mm",
                        "right": "15mm",
                    },
                )

                logger.info("Generated PDF: %s", output_path)
                return output_path

            finally:
                await page.close()

        except asyncio.TimeoutError as e:
            logger.error("PDF conversion timed out after %dms", timeout)
            raise HtmlToPdfError(f"PDF conversion timed out after {timeout}ms") from e
        except Exception as e:
            logger.error("PDF conversion failed: %s", e)
            raise HtmlToPdfError(f"PDF conversion failed: {e}") from e

    async def close(self) -> None:
        """
        Close the browser and cleanup resources.

        Safe to call multiple times.
        """
        async with self._lock:
            if self._browser is not None:
                logger.debug("Closing Playwright browser...")
                await self._browser.close()
                self._browser = None

            if self._playwright is not None:
                await self._playwright.stop()
                self._playwright = None
                logger.info("Playwright browser closed")


# Convenience function for one-off conversions
async def html_to_pdf(
    html: str,
    output_path: Path | str,
    *,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> Path:
    """
    Convert HTML to PDF (convenience function).

    For multiple conversions, use HtmlToPdfConverter context manager
    to reuse the browser instance.

    Args:
        html: HTML content to convert.
        output_path: Path for the output PDF file.
        timeout_ms: Timeout in milliseconds.

    Returns:
        Path to the generated PDF file.

    Raises:
        HtmlToPdfError: If conversion fails.
    """
    async with HtmlToPdfConverter(timeout_ms=timeout_ms) as converter:
        return await converter.convert(html, output_path)


# CLI entry point for testing
if __name__ == "__main__":
    import sys

    async def main():
        if len(sys.argv) < 2:
            # Demo mode with sample HTML
            html = """
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <title>Test PDF</title>
                <style>
                    body { font-family: Arial, sans-serif; padding: 20px; }
                    h1 { color: #333; }
                    .content { margin-top: 20px; }
                </style>
            </head>
            <body>
                <h1>Test PDF Generation</h1>
                <div class="content">
                    <p>This is a test PDF generated from HTML using Playwright.</p>
                    <p>Generated successfully!</p>
                </div>
            </body>
            </html>
            """
            output_path = Path("test_output.pdf")
        else:
            # Read HTML from file
            html_path = Path(sys.argv[1])
            if not html_path.exists():
                print(f"HTML file not found: {html_path}")
                sys.exit(1)
            html = html_path.read_text(encoding="utf-8")
            output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else html_path.with_suffix(".pdf")

        try:
            result = await html_to_pdf(html, output_path)
            print(f"PDF generated: {result}")
        except HtmlToPdfError as e:
            print(f"Error: {e}")
            sys.exit(1)

    logging.basicConfig(level=logging.DEBUG)
    asyncio.run(main())
