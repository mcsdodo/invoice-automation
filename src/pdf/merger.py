"""PDF merger for combining invoice, timesheet, and approval PDFs."""

import logging
from pathlib import Path

from pypdf import PdfReader, PdfWriter

logger = logging.getLogger(__name__)


class PdfMergeError(Exception):
    """Error raised when PDF merging fails."""

    pass


def merge_pdfs(
    invoice_path: Path | str,
    timesheet_path: Path | str,
    approval_path: Path | str,
    output_path: Path | str,
) -> Path:
    """
    Merge three PDFs in order: invoice, timesheet, approval.

    Args:
        invoice_path: Path to the invoice PDF.
        timesheet_path: Path to the timesheet PDF.
        approval_path: Path to the approval email PDF.
        output_path: Path for the merged output PDF.

    Returns:
        Path to the merged PDF file.

    Raises:
        PdfMergeError: If merging fails.
        FileNotFoundError: If any input file doesn't exist.
    """
    invoice_path = Path(invoice_path)
    timesheet_path = Path(timesheet_path)
    approval_path = Path(approval_path)
    output_path = Path(output_path)

    # Validate input files exist
    for path, name in [
        (invoice_path, "Invoice"),
        (timesheet_path, "Timesheet"),
        (approval_path, "Approval"),
    ]:
        if not path.exists():
            raise FileNotFoundError(f"{name} PDF not found: {path}")

    try:
        writer = PdfWriter()

        # Merge in order: invoice -> timesheet -> approval
        for path, name in [
            (invoice_path, "invoice"),
            (timesheet_path, "timesheet"),
            (approval_path, "approval"),
        ]:
            logger.debug("Adding %s: %s", name, path)
            reader = PdfReader(path)
            for page in reader.pages:
                writer.add_page(page)
            logger.debug("Added %d pages from %s", len(reader.pages), name)

        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Write merged PDF
        with open(output_path, "wb") as output_file:
            writer.write(output_file)

        total_pages = len(writer.pages)
        logger.info("Merged %d pages into %s", total_pages, output_path)

        return output_path

    except FileNotFoundError:
        raise
    except Exception as e:
        logger.error("Failed to merge PDFs: %s", e)
        raise PdfMergeError(f"Failed to merge PDFs: {e}") from e


def merge_pdf_files(
    input_paths: list[Path | str],
    output_path: Path | str,
) -> Path:
    """
    Merge multiple PDFs in the order provided.

    This is a more generic version that accepts any number of PDFs.

    Args:
        input_paths: List of paths to input PDFs (in merge order).
        output_path: Path for the merged output PDF.

    Returns:
        Path to the merged PDF file.

    Raises:
        PdfMergeError: If merging fails.
        FileNotFoundError: If any input file doesn't exist.
        ValueError: If no input paths provided.
    """
    if not input_paths:
        raise ValueError("At least one input PDF path is required")

    input_paths = [Path(p) for p in input_paths]
    output_path = Path(output_path)

    # Validate all input files exist
    for path in input_paths:
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {path}")

    try:
        writer = PdfWriter()

        for path in input_paths:
            logger.debug("Adding: %s", path)
            reader = PdfReader(path)
            for page in reader.pages:
                writer.add_page(page)
            logger.debug("Added %d pages from %s", len(reader.pages), path.name)

        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Write merged PDF
        with open(output_path, "wb") as output_file:
            writer.write(output_file)

        total_pages = len(writer.pages)
        logger.info("Merged %d PDFs (%d pages) into %s", len(input_paths), total_pages, output_path)

        return output_path

    except FileNotFoundError:
        raise
    except Exception as e:
        logger.error("Failed to merge PDFs: %s", e)
        raise PdfMergeError(f"Failed to merge PDFs: {e}") from e


# CLI entry point for testing
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 5:
        print("Usage: python -m src.pdf.merger <invoice.pdf> <timesheet.pdf> <approval.pdf> <output.pdf>")
        sys.exit(1)

    logging.basicConfig(level=logging.DEBUG)

    try:
        output = merge_pdfs(
            invoice_path=sys.argv[1],
            timesheet_path=sys.argv[2],
            approval_path=sys.argv[3],
            output_path=sys.argv[4],
        )
        print(f"Merged PDF created: {output}")
    except (PdfMergeError, FileNotFoundError) as e:
        print(f"Error: {e}")
        sys.exit(1)
