"""Data models for the invoice automation workflow."""

from datetime import datetime
from enum import Enum
from pathlib import Path
from pydantic import BaseModel, Field


class WorkflowState(str, Enum):
    """States of the invoice workflow."""

    IDLE = "IDLE"
    PENDING_INIT_APPROVAL = "PENDING_INIT_APPROVAL"
    WAITING_DOCS = "WAITING_DOCS"
    ALL_DOCS_READY = "ALL_DOCS_READY"
    COMPLETE = "COMPLETE"


class TimesheetInfo(BaseModel):
    """Information extracted from a timesheet PDF."""

    total_hours: int
    date_range: str  # e.g., "01/Jan/26 - 31/Jan/26"
    month: int
    year: int

    @property
    def arch_hours(self) -> int:
        """Hours for 'navrh soft. arch.' line (total - 16)."""
        return max(0, self.total_hours - 16)

    @property
    def test_hours(self) -> int:
        """Hours for 'testovanie' line (fixed at 16)."""
        return 16

    @property
    def month_name(self) -> str:
        """Get month name in Slovak."""
        months = [
            "januar", "februar", "marec", "april", "maj", "jun",
            "jul", "august", "september", "oktober", "november", "december"
        ]
        return months[self.month - 1]


class WorkflowData(BaseModel):
    """Persisted workflow state and data."""

    state: WorkflowState = WorkflowState.IDLE

    # Timesheet data
    timesheet_path: Path | None = None
    timesheet_info: TimesheetInfo | None = None

    # Document tracking
    approval_received: bool = False
    invoice_received: bool = False

    # Email thread IDs for reply-to functionality
    manager_thread_id: str | None = None
    accountant_thread_id: str | None = None

    # Downloaded files
    invoice_pdf_path: Path | None = None
    approval_email_html: str | None = None

    # Timeout tracking
    waiting_since: datetime | None = None

    # Telegram message tracking
    telegram_message_id: int | None = None

    def reset(self) -> None:
        """Reset workflow to initial state."""
        self.state = WorkflowState.IDLE
        self.timesheet_path = None
        self.timesheet_info = None
        self.approval_received = False
        self.invoice_received = False
        self.manager_thread_id = None
        self.accountant_thread_id = None
        self.invoice_pdf_path = None
        self.approval_email_html = None
        self.waiting_since = None
        self.telegram_message_id = None


class EmailInfo(BaseModel):
    """Information about a received email."""

    message_id: str
    thread_id: str
    from_email: str
    to_emails: list[str] = Field(default_factory=list)
    cc_emails: list[str] = Field(default_factory=list)
    subject: str
    body_text: str = ""
    body_html: str = ""
    attachments: list[str] = Field(default_factory=list)  # List of attachment filenames
