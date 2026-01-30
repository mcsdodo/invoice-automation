"""PDF parser for extracting data from Jira timesheet PDFs."""

import logging
import re
from pathlib import Path

import pdfplumber

from src.models import TimesheetInfo

logger = logging.getLogger(__name__)


class TimesheetParseError(Exception):
    """Error raised when timesheet parsing fails."""

    pass


def parse_timesheet(pdf_path: Path | str) -> TimesheetInfo:
    """
    Extract timesheet information from a Jira timesheet PDF.

    Args:
        pdf_path: Path to the timesheet PDF file.

    Returns:
        TimesheetInfo with extracted data.

    Raises:
        TimesheetParseError: If extraction fails.
        FileNotFoundError: If the PDF file doesn't exist.
    """
    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        raise FileNotFoundError(f"Timesheet PDF not found: {pdf_path}")

    try:
        text = _extract_text(pdf_path)
        total_hours = _extract_total_hours(text)
        date_range = _extract_date_range(text)
        month, year = _parse_month_year(date_range)

        info = TimesheetInfo(
            total_hours=total_hours,
            date_range=date_range,
            month=month,
            year=year,
        )

        logger.info(
            "Parsed timesheet: %d hours for %s %d",
            info.total_hours,
            info.month_name,
            info.year,
        )

        return info

    except TimesheetParseError:
        raise
    except Exception as e:
        logger.error("Failed to parse timesheet %s: %s", pdf_path, e)
        raise TimesheetParseError(f"Failed to parse timesheet: {e}") from e


def _extract_text(pdf_path: Path) -> str:
    """Extract all text from PDF."""
    text_parts = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)

    full_text = "\n".join(text_parts)

    if not full_text.strip():
        raise TimesheetParseError("No text could be extracted from PDF")

    logger.debug("Extracted %d characters from PDF", len(full_text))
    return full_text


def _extract_total_hours(text: str) -> int:
    """
    Extract total hours from timesheet text.

    Looks for patterns like:
    - "Total: 160h"
    - "Total Hours: 160"
    - "Logged: 160h"
    - Lines ending with total hours value
    """
    # Common patterns for total hours in Jira timesheets
    patterns = [
        # "Total: 160h" or "Total: 160 h"
        r"Total[:\s]+(\d+)\s*h",
        # "Total Hours: 160"
        r"Total\s+Hours[:\s]+(\d+)",
        # "Logged: 160h"
        r"Logged[:\s]+(\d+)\s*h",
        # "Sum: 160h"
        r"Sum[:\s]+(\d+)\s*h",
        # "160h total"
        r"(\d+)\s*h\s+total",
        # Look for standalone hour values at end of document (common in summaries)
        r"\b(\d{2,3})\s*h?\s*$",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            hours = int(match.group(1))
            # Sanity check: hours should be reasonable (1-500 for monthly timesheet)
            if 1 <= hours <= 500:
                logger.debug("Found total hours: %d (pattern: %s)", hours, pattern)
                return hours

    # Fallback: look for the largest reasonable hour value in the document
    all_hours = re.findall(r"\b(\d{2,3})\s*h\b", text, re.IGNORECASE)
    if all_hours:
        hours_values = [int(h) for h in all_hours if 1 <= int(h) <= 500]
        if hours_values:
            # The total is likely the largest value
            max_hours = max(hours_values)
            logger.debug("Found total hours via fallback (max): %d", max_hours)
            return max_hours

    raise TimesheetParseError("Could not extract total hours from timesheet")


def _extract_date_range(text: str) -> str:
    """
    Extract date range from timesheet text.

    Expects format like: "01/Jan/26 - 31/Jan/26"
    """
    # Pattern for "DD/Mon/YY - DD/Mon/YY"
    pattern = r"(\d{1,2}/[A-Za-z]{3}/\d{2})\s*[-–—]\s*(\d{1,2}/[A-Za-z]{3}/\d{2})"
    match = re.search(pattern, text)
    if match:
        date_range = f"{match.group(1)} - {match.group(2)}"
        logger.debug("Found date range: %s", date_range)
        return date_range

    # Alternative patterns
    alt_patterns = [
        # "01 Jan 2026 - 31 Jan 2026"
        r"(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})\s*[-–—]\s*(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})",
        # "January 1-31, 2026"
        r"([A-Za-z]+)\s+(\d{1,2})\s*[-–—]\s*(\d{1,2}),?\s*(\d{4})",
        # "2026-01-01 - 2026-01-31"
        r"(\d{4}-\d{2}-\d{2})\s*[-–—]\s*(\d{4}-\d{2}-\d{2})",
    ]

    for alt_pattern in alt_patterns:
        match = re.search(alt_pattern, text)
        if match:
            # Normalize to expected format if possible
            date_range = " - ".join(match.groups()[:2]) if len(match.groups()) <= 2 else match.group(0)
            logger.debug("Found date range (alt): %s", date_range)
            return date_range

    raise TimesheetParseError("Could not extract date range from timesheet")


def _parse_month_year(date_range: str) -> tuple[int, int]:
    """
    Parse month and year from date range string.

    Args:
        date_range: String like "01/Jan/26 - 31/Jan/26"

    Returns:
        Tuple of (month, year) where month is 1-12 and year is 4-digit.
    """
    month_map = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4,
        "may": 5, "jun": 6, "jul": 7, "aug": 8,
        "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        "january": 1, "february": 2, "march": 3, "april": 4,
        "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
    }

    # Try to extract month name
    month_match = re.search(r"([A-Za-z]{3,})", date_range)
    if not month_match:
        raise TimesheetParseError(f"Could not extract month from date range: {date_range}")

    month_str = month_match.group(1).lower()
    month = month_map.get(month_str[:3])
    if month is None:
        raise TimesheetParseError(f"Unknown month: {month_str}")

    # Try to extract year (2-digit or 4-digit)
    year_match = re.search(r"/(\d{2})(?:\s|$|-)|(\d{4})", date_range)
    if not year_match:
        raise TimesheetParseError(f"Could not extract year from date range: {date_range}")

    year_str = year_match.group(1) or year_match.group(2)
    year = int(year_str)

    # Convert 2-digit year to 4-digit
    if year < 100:
        # Assume 20xx for years 00-99
        year = 2000 + year

    logger.debug("Parsed month=%d, year=%d from '%s'", month, year, date_range)
    return month, year


# CLI entry point for testing
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m src.pdf.parser <timesheet.pdf>")
        sys.exit(1)

    logging.basicConfig(level=logging.DEBUG)

    try:
        info = parse_timesheet(sys.argv[1])
        print(f"Total hours: {info.total_hours}")
        print(f"Date range: {info.date_range}")
        print(f"Month: {info.month} ({info.month_name})")
        print(f"Year: {info.year}")
        print(f"Architecture hours: {info.arch_hours}")
        print(f"Testing hours: {info.test_hours}")
    except TimesheetParseError as e:
        print(f"Parse error: {e}")
        sys.exit(1)
    except FileNotFoundError as e:
        print(f"File not found: {e}")
        sys.exit(1)
