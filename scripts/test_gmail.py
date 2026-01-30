"""Quick test for Gmail API credentials.

First run will open browser for OAuth consent.
Subsequent runs will use saved token.
"""
import os
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]

credentials_file = os.getenv("GMAIL_CREDENTIALS_FILE", "config/credentials.json")
token_file = os.getenv("GMAIL_TOKEN_FILE", "config/token.json")

def get_credentials():
    creds = None

    # Load existing token
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)

    # Refresh or get new token
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Refreshing expired token...")
            creds.refresh(Request())
        else:
            print("Starting OAuth flow (browser will open)...")
            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
            creds = flow.run_local_server(port=0)

        # Save token
        with open(token_file, "w") as f:
            f.write(creds.to_json())
        print(f"Token saved to {token_file}")

    return creds

def main():
    creds = get_credentials()
    service = build("gmail", "v1", credentials=creds)

    # Get profile
    profile = service.users().getProfile(userId="me").execute()
    print(f"Gmail API: Authenticated as {profile['emailAddress']}")
    print(f"Total messages: {profile.get('messagesTotal', 'N/A')}")

if __name__ == "__main__":
    main()
