#!/usr/bin/env python
"""Step 2: Create and drop a test timesheet PDF into the watch folder."""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

def create_timesheet(output_path: Path, total_hours: int = 160) -> None:
    """Create a test timesheet PDF."""
    c = canvas.Canvas(str(output_path), pagesize=A4)
    width, height = A4

    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, height - 50, "Jira Timesheet Export")

    c.setFont("Helvetica", 12)
    c.drawString(50, height - 80, "Period: 01/Jan/26 - 31/Jan/26")
    c.drawString(50, height - 110, "Project: YourCompany inc. Navigation App")
    c.drawString(50, height - 130, "User: Test User")

    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, height - 170, "Time Logged:")

    c.setFont("Helvetica", 11)
    c.drawString(70, height - 195, f"Software Architecture: {total_hours - 16}h")
    c.drawString(70, height - 215, "Testing: 16h")

    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, height - 260, f"Total: {total_hours}h")

    c.save()


if __name__ == "__main__":
    hours = int(sys.argv[1]) if len(sys.argv) > 1 else 160

    output = Path("data/incoming/timesheet_test.pdf")
    output.parent.mkdir(parents=True, exist_ok=True)

    create_timesheet(output, hours)

    print("=" * 60)
    print("STEP 2: Timesheet PDF Created")
    print("=" * 60)
    print()
    print(f"  File: {output}")
    print(f"  Hours: {hours}")
    print()
    print("NEXT: Check Telegram for approval message.")
    print("      Click 'Approve' to send emails.")
    print()
