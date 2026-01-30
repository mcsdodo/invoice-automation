#!/usr/bin/env python
"""Step 4: Send invoice reply with PDF attachment to the accountant thread."""

import base64
import json
import sys
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from src.gmail.auth import get_gmail_service
from src.config import settings


def create_invoice_pdf(output_path: Path, hours: int = 160, rate: int = 10) -> None:
    """Create a test invoice PDF."""
    total = hours * rate

    c = canvas.Canvas(str(output_path), pagesize=A4)
    width, height = A4

    c.setFont("Helvetica-Bold", 20)
    c.drawString(50, height - 50, "INVOICE")

    c.setFont("Helvetica", 12)
    c.drawString(50, height - 90, "Invoice #: 2026-001")
    c.drawString(50, height - 110, "Date: January 30, 2026")

    c.drawString(50, height - 150, "From: Accountant Services")
    c.drawString(50, height - 170, "To: YourCompany inc.")

    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, height - 210, "Services:")

    c.setFont("Helvetica", 11)
    c.drawString(70, height - 235, f"navrh soft. arch. pre nav. aplikaciu - {hours - 16}h")
    c.drawString(70, height - 255, "testovanie navigacnej apl. pocas jazdy - 16h")

    c.setFont("Helvetica", 12)
    c.drawString(50, height - 295, f"Hours: {hours}")
    c.drawString(50, height - 315, f"Rate: {rate} EUR/h")

    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, height - 355, f"Total: {total} EUR (bez DPH)")

    c.save()


def send_invoice_reply():
    """Send an invoice reply with PDF to the accountant thread."""
    state_file = Path("data/state.json")
    if not state_file.exists():
        print("ERROR: No state file. Run previous steps first.")
        return False

    state = json.loads(state_file.read_text())
    thread_id = state.get("accountant_thread_id")

    if not thread_id:
        print("ERROR: No accountant thread ID. Emails not sent yet?")
        return False

    if state.get("invoice_received"):
        print("NOTE: Invoice already received.")
        return True

    # Create invoice PDF
    invoice_path = Path("data/temp/test_invoice.pdf")
    invoice_path.parent.mkdir(parents=True, exist_ok=True)

    timesheet_info = state.get("timesheet_info", {})
    hours = timesheet_info.get("total_hours", 160)
    create_invoice_pdf(invoice_path, hours, settings.hourly_rate)
    print(f"Created invoice PDF: {invoice_path}")

    service = get_gmail_service()

    # Get the original message to reply to
    thread = service.users().threads().get(userId="me", id=thread_id).execute()
    messages = thread.get("messages", [])
    if not messages:
        print("ERROR: No messages in thread.")
        return False

    original_msg = messages[0]
    headers = {h["name"]: h["value"] for h in original_msg["payload"]["headers"]}
    subject = headers.get("Subject", "")
    message_id = headers.get("Message-ID", "")

    # Create reply with attachment
    msg = MIMEMultipart()
    msg["To"] = settings.from_email
    msg["From"] = settings.from_email
    msg["Subject"] = f"Re: {subject}" if not subject.startswith("Re:") else subject
    msg["In-Reply-To"] = message_id
    msg["References"] = message_id

    msg.attach(MIMEText("V prilohe faktura.\n\nS pozdravom,\nAccountant"))

    with open(invoice_path, "rb") as f:
        attachment = MIMEApplication(f.read(), _subtype="pdf")
        attachment.add_header("Content-Disposition", "attachment", filename="faktura_2026_01.pdf")
        msg.attach(attachment)

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    service.users().messages().send(
        userId="me",
        body={"raw": raw, "threadId": thread_id}
    ).execute()

    print("Invoice reply sent!")
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("STEP 4: Sending Accountant Invoice")
    print("=" * 60)
    print()

    if send_invoice_reply():
        print()
        print("NEXT: Wait for service to detect both emails (~60s)")
        print("      Then approve final merge in Telegram.")
        print()
