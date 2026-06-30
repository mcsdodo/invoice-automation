"""Google Drive service built from the shared Gmail OAuth credentials."""

import logging

from googleapiclient.discovery import build, Resource

from src.gmail.auth import get_credentials

logger = logging.getLogger(__name__)

# Full Drive scope is required: Drive OAuth scopes are not folder-scoped, and
# drive.file cannot see files the app did not create (timesheets are dropped by
# the user). Moving a processed file to processed/ is a write to such a file.
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"


def get_drive_service() -> Resource:
    """Build an authenticated Drive v3 service from the shared credentials."""
    creds = get_credentials()
    service = build("drive", "v3", credentials=creds)
    logger.debug("Drive service created")
    return service
