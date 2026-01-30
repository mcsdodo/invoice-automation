"""Gmail inbox monitor module.

Polls Gmail inbox for new emails matching specified criteria.
"""

import asyncio
import base64
import logging
import time
from datetime import datetime
from pathlib import Path

from googleapiclient.discovery import Resource
from googleapiclient.errors import HttpError

from src.gmail.auth import get_gmail_service
from src.config import settings
from src.models import EmailInfo

logger = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES = 5
INITIAL_BACKOFF_SECONDS = 1
MAX_BACKOFF_SECONDS = 60
NETWORK_FAILURE_THRESHOLD = 3


class GmailMonitor:
    """Monitors Gmail inbox for new emails.

    Polls the inbox at a configurable interval, filters by sender,
    and downloads PDF attachments.

    Attributes:
        poll_interval: Seconds between inbox polls (default 60).
        service: Authenticated Gmail API service.
    """

    def __init__(
        self,
        poll_interval: int = 60,
        service: Resource | None = None,
        temp_dir: Path | None = None,
    ):
        """Initialize the Gmail monitor.

        Args:
            poll_interval: Seconds between inbox polls.
            service: Gmail API service (created if not provided).
            temp_dir: Directory for downloaded attachments (default data/temp).
        """
        self.poll_interval = poll_interval
        self._service = service
        self._temp_dir = temp_dir or Path("data/temp")
        self._last_history_id: str | None = None
        self._consecutive_failures = 0
        self._running = False

    @property
    def service(self) -> Resource:
        """Get or create Gmail API service."""
        if self._service is None:
            self._service = get_gmail_service()
        return self._service

    def _refresh_service(self) -> None:
        """Refresh the Gmail API service (e.g., after auth error)."""
        logger.info("Refreshing Gmail API service")
        self._service = get_gmail_service()

    async def _exponential_backoff(self, attempt: int) -> None:
        """Wait with exponential backoff.

        Args:
            attempt: Current attempt number (0-indexed).
        """
        wait_time = min(INITIAL_BACKOFF_SECONDS * (2**attempt), MAX_BACKOFF_SECONDS)
        logger.debug("Backing off for %d seconds (attempt %d)", wait_time, attempt + 1)
        await asyncio.sleep(wait_time)

    def _get_messages_by_query(self, query: str, max_results: int = 10) -> list[dict]:
        """Get messages matching a query.

        Args:
            query: Gmail search query.
            max_results: Maximum number of messages to return.

        Returns:
            List of message metadata dicts.
        """
        response = (
            self.service.users()
            .messages()
            .list(userId="me", q=query, maxResults=max_results)
            .execute()
        )
        return response.get("messages", [])

    def _get_message_detail(self, message_id: str) -> dict:
        """Get full message details.

        Args:
            message_id: Gmail message ID.

        Returns:
            Full message dict from API.
        """
        return (
            self.service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )

    def _extract_header(self, headers: list[dict], name: str) -> str:
        """Extract a header value from message headers.

        Args:
            headers: List of header dicts with name/value keys.
            name: Header name to find.

        Returns:
            Header value or empty string if not found.
        """
        for header in headers:
            if header.get("name", "").lower() == name.lower():
                return header.get("value", "")
        return ""

    def _extract_email_addresses(self, header_value: str) -> list[str]:
        """Extract email addresses from a header value.

        Handles formats like:
        - "email@example.com"
        - "Name <email@example.com>"
        - "email1@example.com, email2@example.com"

        Args:
            header_value: Raw header value.

        Returns:
            List of email addresses.
        """
        if not header_value:
            return []

        addresses = []
        for part in header_value.split(","):
            part = part.strip()
            if "<" in part and ">" in part:
                # "Name <email@example.com>" format
                email = part[part.index("<") + 1 : part.index(">")]
                addresses.append(email.lower())
            elif "@" in part:
                addresses.append(part.lower())
        return addresses

    def _extract_body(self, payload: dict) -> tuple[str, str]:
        """Extract plain text and HTML body from message payload.

        Args:
            payload: Message payload dict.

        Returns:
            Tuple of (body_text, body_html).
        """
        body_text = ""
        body_html = ""

        def process_part(part: dict) -> None:
            nonlocal body_text, body_html

            mime_type = part.get("mimeType", "")
            body = part.get("body", {})

            if "data" in body:
                decoded = base64.urlsafe_b64decode(body["data"]).decode("utf-8", errors="replace")
                if mime_type == "text/plain" and not body_text:
                    body_text = decoded
                elif mime_type == "text/html" and not body_html:
                    body_html = decoded

            # Process nested parts
            for subpart in part.get("parts", []):
                process_part(subpart)

        process_part(payload)
        return body_text, body_html

    def _download_attachment(
        self, message_id: str, attachment_id: str, filename: str
    ) -> Path:
        """Download an attachment to the temp directory.

        Args:
            message_id: Gmail message ID.
            attachment_id: Attachment ID.
            filename: Original filename.

        Returns:
            Path to the downloaded file.
        """
        # Ensure temp directory exists
        self._temp_dir.mkdir(parents=True, exist_ok=True)

        # Get attachment data
        attachment = (
            self.service.users()
            .messages()
            .attachments()
            .get(userId="me", messageId=message_id, id=attachment_id)
            .execute()
        )

        data = base64.urlsafe_b64decode(attachment["data"])

        # Generate unique filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Keep original extension if present
        if "." in filename:
            base_name, ext = filename.rsplit(".", 1)
            new_filename = f"invoice_{timestamp}.{ext}"
        else:
            new_filename = f"invoice_{timestamp}"

        filepath = self._temp_dir / new_filename
        filepath.write_bytes(data)
        logger.info("Downloaded attachment to %s", filepath)
        return filepath

    def _extract_attachments(
        self, message_id: str, payload: dict
    ) -> list[tuple[str, Path | None]]:
        """Extract attachment info and optionally download PDFs.

        Args:
            message_id: Gmail message ID.
            payload: Message payload dict.

        Returns:
            List of (filename, downloaded_path) tuples.
            downloaded_path is None for non-PDF attachments.
        """
        attachments = []

        def process_part(part: dict) -> None:
            filename = part.get("filename", "")
            body = part.get("body", {})
            attachment_id = body.get("attachmentId")

            if filename and attachment_id:
                downloaded_path = None
                # Download PDF attachments
                if filename.lower().endswith(".pdf"):
                    try:
                        downloaded_path = self._download_attachment(
                            message_id, attachment_id, filename
                        )
                    except Exception as e:
                        logger.error("Failed to download attachment %s: %s", filename, e)
                attachments.append((filename, downloaded_path))

            # Process nested parts
            for subpart in part.get("parts", []):
                process_part(subpart)

        process_part(payload)
        return attachments

    def _parse_message(self, message: dict, download_attachments: bool = True) -> EmailInfo:
        """Parse a Gmail message into EmailInfo.

        Args:
            message: Full message dict from API.
            download_attachments: Whether to download PDF attachments.

        Returns:
            EmailInfo with parsed data.
        """
        payload = message.get("payload", {})
        headers = payload.get("headers", [])

        # Extract headers
        from_email = self._extract_email_addresses(self._extract_header(headers, "From"))
        to_emails = self._extract_email_addresses(self._extract_header(headers, "To"))
        cc_emails = self._extract_email_addresses(self._extract_header(headers, "Cc"))
        subject = self._extract_header(headers, "Subject")

        # Extract body
        body_text, body_html = self._extract_body(payload)

        # Extract attachments
        attachment_names = []
        if download_attachments:
            attachments = self._extract_attachments(message["id"], payload)
            attachment_names = [name for name, _ in attachments]
        else:
            # Just get names without downloading
            def get_attachment_names(part: dict) -> list[str]:
                names = []
                filename = part.get("filename", "")
                if filename and part.get("body", {}).get("attachmentId"):
                    names.append(filename)
                for subpart in part.get("parts", []):
                    names.extend(get_attachment_names(subpart))
                return names

            attachment_names = get_attachment_names(payload)

        return EmailInfo(
            message_id=message["id"],
            thread_id=message["threadId"],
            from_email=from_email[0] if from_email else "",
            to_emails=to_emails,
            cc_emails=cc_emails,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            attachments=attachment_names,
        )

    async def check_for_emails(
        self,
        from_email: str | None = None,
        thread_id: str | None = None,
        unread_only: bool = True,
        mark_as_read: bool = True,
        max_results: int = 10,
    ) -> list[EmailInfo]:
        """Check for new emails matching criteria.

        Args:
            from_email: Filter by sender email address.
            thread_id: Filter by thread ID (for checking replies).
            unread_only: Only return unread messages.
            mark_as_read: Mark returned messages as read.
            max_results: Maximum number of messages to return.

        Returns:
            List of EmailInfo for matching messages.

        Raises:
            HttpError: On API errors after retries exhausted.
        """
        # Build query
        query_parts = []
        if from_email:
            query_parts.append(f"from:{from_email}")
        if unread_only:
            query_parts.append("is:unread")
        if thread_id:
            query_parts.append(f"thread:{thread_id}")

        query = " ".join(query_parts) if query_parts else "is:unread"
        logger.debug("Checking for emails with query: %s", query)

        # Execute with retry
        for attempt in range(MAX_RETRIES):
            try:
                messages = self._get_messages_by_query(query, max_results)
                self._consecutive_failures = 0
                break
            except HttpError as e:
                if e.resp.status == 429:
                    # Rate limited
                    logger.warning("Rate limited, backing off")
                    await self._exponential_backoff(attempt)
                elif e.resp.status in (401, 403):
                    # Auth error
                    logger.warning("Auth error, refreshing service")
                    self._refresh_service()
                else:
                    self._consecutive_failures += 1
                    if self._consecutive_failures >= NETWORK_FAILURE_THRESHOLD:
                        logger.error(
                            "Network failures threshold reached (%d)",
                            self._consecutive_failures,
                        )
                        raise
                    await self._exponential_backoff(attempt)

                if attempt == MAX_RETRIES - 1:
                    raise
            except Exception as e:
                self._consecutive_failures += 1
                logger.warning("Error checking emails (attempt %d): %s", attempt + 1, e)
                if attempt == MAX_RETRIES - 1:
                    raise
                await self._exponential_backoff(attempt)
        else:
            return []

        if not messages:
            logger.debug("No matching messages found")
            return []

        # Parse messages
        results = []
        for msg_meta in messages:
            try:
                message = self._get_message_detail(msg_meta["id"])
                email_info = self._parse_message(message)
                results.append(email_info)

                # Mark as read if requested
                if mark_as_read:
                    self._mark_as_read(msg_meta["id"])

            except Exception as e:
                logger.error("Error parsing message %s: %s", msg_meta["id"], e)

        logger.info("Found %d matching emails", len(results))
        return results

    def _mark_as_read(self, message_id: str) -> None:
        """Mark a message as read.

        Args:
            message_id: Gmail message ID.
        """
        try:
            self.service.users().messages().modify(
                userId="me",
                id=message_id,
                body={"removeLabelIds": ["UNREAD"]},
            ).execute()
            logger.debug("Marked message %s as read", message_id)
        except Exception as e:
            logger.warning("Failed to mark message %s as read: %s", message_id, e)

    async def poll_once(
        self,
        from_email: str | None = None,
        thread_id: str | None = None,
    ) -> list[EmailInfo]:
        """Perform a single poll for new emails.

        Args:
            from_email: Filter by sender email address.
            thread_id: Filter by thread ID.

        Returns:
            List of EmailInfo for new messages.
        """
        return await self.check_for_emails(
            from_email=from_email,
            thread_id=thread_id,
            unread_only=True,
            mark_as_read=True,
        )

    async def start_polling(
        self,
        from_emails: list[str] | None = None,
        callback=None,
    ) -> None:
        """Start continuous polling for new emails.

        Args:
            from_emails: List of sender emails to watch for.
            callback: Async function called with each EmailInfo.
                     If None, emails are logged but not processed.
        """
        self._running = True
        logger.info("Starting Gmail monitor, polling every %ds", self.poll_interval)

        while self._running:
            try:
                # Check for emails from each sender
                if from_emails:
                    for from_email in from_emails:
                        emails = await self.poll_once(from_email=from_email)
                        if callback:
                            for email_info in emails:
                                await callback(email_info)
                else:
                    emails = await self.poll_once()
                    if callback:
                        for email_info in emails:
                            await callback(email_info)

            except Exception as e:
                logger.error("Error during poll: %s", e)

            # Wait for next poll
            await asyncio.sleep(self.poll_interval)

    def stop_polling(self) -> None:
        """Stop the polling loop."""
        logger.info("Stopping Gmail monitor")
        self._running = False

    def get_downloaded_invoice_path(self, email_info: EmailInfo) -> Path | None:
        """Get the path to a downloaded invoice PDF.

        Looks for the most recent invoice_*.pdf in the temp directory
        that matches the email's attachments.

        Args:
            email_info: EmailInfo with attachment names.

        Returns:
            Path to downloaded PDF or None if not found.
        """
        pdf_attachments = [a for a in email_info.attachments if a.lower().endswith(".pdf")]
        if not pdf_attachments:
            return None

        # Find matching downloaded file
        # Look for invoice_*.pdf files in temp dir
        for pdf_file in sorted(self._temp_dir.glob("invoice_*.pdf"), reverse=True):
            # Return most recent
            return pdf_file

        return None
