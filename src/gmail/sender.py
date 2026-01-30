"""Gmail email sender module.

Handles sending emails with attachments and replying to threads.
"""

import base64
import logging
import mimetypes
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders
from pathlib import Path

from googleapiclient.discovery import Resource

from src.gmail.auth import get_gmail_service
from src.config import settings

logger = logging.getLogger(__name__)


def _create_message(
    to: str,
    subject: str,
    body: str,
    cc: str | None = None,
    attachment_path: Path | None = None,
    thread_id: str | None = None,
    in_reply_to: str | None = None,
    references: str | None = None,
) -> dict:
    """Create an email message for the Gmail API.

    Args:
        to: Recipient email address.
        subject: Email subject.
        body: Email body (plain text).
        cc: CC recipient email address.
        attachment_path: Path to file to attach.
        thread_id: Thread ID for replies.
        in_reply_to: Message-ID for reply threading.
        references: References header for threading.

    Returns:
        Gmail API message dict with raw encoded content.
    """
    # Create message with attachment if provided
    if attachment_path:
        message = MIMEMultipart()
        message.attach(MIMEText(body, "plain"))

        # Add attachment
        attachment_path = Path(attachment_path)
        content_type, _ = mimetypes.guess_type(str(attachment_path))
        if content_type is None:
            content_type = "application/octet-stream"

        main_type, sub_type = content_type.split("/", 1)

        with open(attachment_path, "rb") as f:
            attachment = MIMEBase(main_type, sub_type)
            attachment.set_payload(f.read())

        encoders.encode_base64(attachment)
        attachment.add_header(
            "Content-Disposition",
            "attachment",
            filename=attachment_path.name,
        )
        message.attach(attachment)
    else:
        message = MIMEText(body, "plain")

    # Set headers
    message["to"] = to
    message["from"] = settings.from_email
    message["subject"] = subject

    if cc:
        message["cc"] = cc

    # Set threading headers for replies
    if in_reply_to:
        message["In-Reply-To"] = in_reply_to
    if references:
        message["References"] = references

    # Encode message
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

    result = {"raw": raw}
    if thread_id:
        result["threadId"] = thread_id

    return result


def _send_message(service: Resource, message: dict) -> dict:
    """Send a message via Gmail API.

    Args:
        service: Authenticated Gmail API service.
        message: Message dict with raw content and optional threadId.

    Returns:
        Gmail API response with id, threadId, labelIds.
    """
    result = service.users().messages().send(userId="me", body=message).execute()
    logger.info("Message sent: id=%s, threadId=%s", result.get("id"), result.get("threadId"))
    return result


def send_email(
    to: str,
    subject: str,
    body: str,
    cc: str | None = None,
    attachment_path: Path | None = None,
    service: Resource | None = None,
) -> tuple[str, str]:
    """Send an email with optional CC and attachment.

    Args:
        to: Recipient email address.
        subject: Email subject.
        body: Email body (plain text).
        cc: CC recipient email address.
        attachment_path: Path to file to attach.
        service: Gmail API service (created if not provided).

    Returns:
        Tuple of (message_id, thread_id).

    Raises:
        googleapiclient.errors.HttpError: On API errors.
    """
    if service is None:
        service = get_gmail_service()

    message = _create_message(
        to=to,
        subject=subject,
        body=body,
        cc=cc,
        attachment_path=attachment_path,
    )

    result = _send_message(service, message)
    return result["id"], result["threadId"]


def reply_to_thread(
    thread_id: str,
    body: str,
    attachment_path: Path | None = None,
    service: Resource | None = None,
) -> tuple[str, str]:
    """Reply to an existing email thread.

    Fetches the original message to get subject and threading headers,
    then sends a reply that will appear in the same thread.

    Args:
        thread_id: Gmail thread ID to reply to.
        body: Reply body (plain text).
        attachment_path: Path to file to attach.
        service: Gmail API service (created if not provided).

    Returns:
        Tuple of (message_id, thread_id).

    Raises:
        googleapiclient.errors.HttpError: On API errors.
        ValueError: If thread not found or has no messages.
    """
    if service is None:
        service = get_gmail_service()

    # Get thread to find original message headers
    thread = (
        service.users()
        .threads()
        .get(userId="me", id=thread_id, format="metadata", metadataHeaders=["Subject", "Message-ID", "From", "To"])
        .execute()
    )

    messages = thread.get("messages", [])
    if not messages:
        raise ValueError(f"Thread {thread_id} has no messages")

    # Get the first message for subject and original recipient
    first_msg = messages[0]
    # Get the last message for reply headers
    last_msg = messages[-1]

    # Extract headers from first message
    first_headers = {h["name"]: h["value"] for h in first_msg.get("payload", {}).get("headers", [])}
    last_headers = {h["name"]: h["value"] for h in last_msg.get("payload", {}).get("headers", [])}

    subject = first_headers.get("Subject", "")
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"

    # Get the original recipient (to reply to)
    # If we sent the first message, reply to the From of the last message
    # If someone else sent the first message, reply to them
    original_from = last_headers.get("From", first_headers.get("From", ""))
    # Extract just the email address if it's in "Name <email>" format
    if "<" in original_from and ">" in original_from:
        original_to = original_from[original_from.index("<") + 1:original_from.index(">")]
    else:
        original_to = original_from

    # Get Message-ID for threading
    in_reply_to = last_headers.get("Message-ID")
    references = last_headers.get("References", "")
    if in_reply_to:
        if references:
            references = f"{references} {in_reply_to}"
        else:
            references = in_reply_to

    message = _create_message(
        to=original_to,
        subject=subject,
        body=body,
        attachment_path=attachment_path,
        thread_id=thread_id,
        in_reply_to=in_reply_to,
        references=references,
    )

    result = _send_message(service, message)
    return result["id"], result["threadId"]
