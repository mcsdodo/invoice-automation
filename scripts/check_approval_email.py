"""Check for the approval email in the manager thread."""
import json
from pathlib import Path
from src.gmail.auth import get_gmail_service
from src.gmail.monitor import GmailMonitor

# Load state to get thread ID
state = json.loads(Path("data/state.json").read_text())
manager_thread_id = state["manager_thread_id"]
print(f"Manager thread ID: {manager_thread_id}")

# Check for emails in that thread (including read ones)
monitor = GmailMonitor()
service = monitor.service

# Get all messages in the thread
thread = service.users().threads().get(userId="me", id=manager_thread_id).execute()
messages = thread.get("messages", [])

print(f"\nFound {len(messages)} messages in thread:")
for msg in messages:
    headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
    labels = msg.get("labelIds", [])
    print(f"  - ID: {msg['id']}")
    print(f"    From: {headers.get('From', 'N/A')}")
    print(f"    Subject: {headers.get('Subject', 'N/A')}")
    print(f"    Labels: {labels}")
    print()

# If there's more than 1 message, the second one is the reply
if len(messages) > 1:
    reply = messages[-1]  # Last message is the reply
    print("Reply found! Let's process it as approval...")

    # Parse the reply
    email_info = monitor._parse_message(reply, download_attachments=False)
    print(f"From: {email_info.from_email}")
    print(f"Body: {email_info.body_text[:200]}...")

    # Check for approval keywords
    from src.config import settings
    body_lower = email_info.body_text.lower()
    is_approval = any(kw in body_lower for kw in settings.approval_keywords_list)
    print(f"\nContains approval keyword: {is_approval}")
