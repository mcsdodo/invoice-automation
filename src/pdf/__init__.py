"""PDF processing module for invoice automation.

This module provides:
- Timesheet PDF parsing (extract hours, dates)
- PDF merging (invoice + timesheet + approval)
- HTML to PDF conversion (for approval emails)
"""

from src.pdf.html_to_pdf import HtmlToPdfConverter, HtmlToPdfError, html_to_pdf
from src.pdf.merger import PdfMergeError, merge_pdf_files, merge_pdfs
from src.pdf.parser import TimesheetParseError, parse_timesheet

__all__ = [
    # Parser
    "parse_timesheet",
    "TimesheetParseError",
    # Merger
    "merge_pdfs",
    "merge_pdf_files",
    "PdfMergeError",
    # HTML to PDF
    "HtmlToPdfConverter",
    "html_to_pdf",
    "HtmlToPdfError",
]
