#!/usr/bin/env python
"""Step 3: Send approval reply to the manager email thread."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.gmail.auth import get_gmail_service
from src.config import settings


def send_approval_reply():
    """Send an approval reply to the manager thread."""
    state_file = Path("data/state.json")
    if not state_file.exists():
        print("ERROR: No state file. Run step 1 and 2 first.")
        return False

    state = json.loads(state_file.read_text())
    thread_id = state.get("manager_thread_id")

    if not thread_id:
        print("ERROR: No manager thread ID. Emails not sent yet?")
        return False

    if state.get("approval_received"):
        print("NOTE: Approval already received.")
        return True

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

    # Create reply
    import base64
    from email.mime.text import MIMEText

    reply = MIMEText("ok schvalujem\n\nS pozdravom,\nManager")
    reply["To"] = settings.from_email
    reply["From"] = settings.from_email  # Same account for testing
    reply["Subject"] = f"Re: {subject}" if not subject.startswith("Re:") else subject
    reply["In-Reply-To"] = message_id
    reply["References"] = message_id

    raw = base64.urlsafe_b64encode(reply.as_bytes()).decode()
    service.users().messages().send(
        userId="me",
        body={"raw": raw, "threadId": thread_id}
    ).execute()

    print("Approval reply sent!")
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("STEP 3: Sending Manager Approval")
    print("=" * 60)
    print()

    if send_approval_reply():
        print()
        print("NEXT: Wait for service to detect the email (~60s)")
        print("      Or run step 4 to send invoice.")
        print()
