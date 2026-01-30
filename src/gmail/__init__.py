"""Gmail integration module.

Provides authentication, sending, and monitoring for Gmail API.
"""

from src.gmail.auth import get_gmail_service, get_credentials
from src.gmail.sender import send_email, reply_to_thread
from src.gmail.monitor import GmailMonitor

__all__ = [
    "get_gmail_service",
    "get_credentials",
    "send_email",
    "reply_to_thread",
    "GmailMonitor",
]
