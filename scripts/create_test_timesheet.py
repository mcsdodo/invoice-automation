"""Create a test timesheet PDF for testing the workflow."""

from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


def create_test_timesheet(output_path: Path, total_hours: int = 160) -> None:
    """Create a simple test timesheet PDF.

    Args:
        output_path: Where to save the PDF.
        total_hours: Total hours to show on timesheet.
    """
    c = canvas.Canvas(str(output_path), pagesize=A4)
    width, height = A4

    # Title
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, height - 50, "Jira Timesheet Export")

    # Date range
    c.setFont("Helvetica", 12)
    c.drawString(50, height - 80, "Period: 01/Jan/26 - 31/Jan/26")

    # Project info
    c.drawString(50, height - 110, "Project: YourCompany inc. Navigation App")
    c.drawString(50, height - 130, "User: Jozef Lacny")

    # Hours breakdown
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, height - 170, "Time Logged:")

    c.setFont("Helvetica", 11)
    c.drawString(70, height - 195, f"Software Architecture: {total_hours - 16}h")
    c.drawString(70, height - 215, "Testing: 16h")

    # Total
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, height - 260, f"Total: {total_hours}h")

    c.save()
    print(f"Created test timesheet: {output_path}")


if __name__ == "__main__":
    import sys
    hours = int(sys.argv[1]) if len(sys.argv) > 1 else 160
    output = Path("data/incoming/timesheet_test.pdf")
    output.parent.mkdir(parents=True, exist_ok=True)
    create_test_timesheet(output, hours)
