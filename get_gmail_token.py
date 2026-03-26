"""
Run this once to generate your Gmail OAuth refresh token.
It will open a browser window for you to authorize access.

Usage:
    python get_gmail_token.py
"""

import json
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",   # for archiving (labeling)
    "https://www.googleapis.com/auth/gmail.send",     # for sending digest emails
]

def main():
    flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
    creds = flow.run_local_server(port=0)

    print("\n✓ Authorization successful\n")
    print("Copy these three values into your .env file:\n")
    print(f"GMAIL_CLIENT_ID={creds.client_id}")
    print(f"GMAIL_CLIENT_SECRET={creds.client_secret}")
    print(f"GMAIL_REFRESH_TOKEN={creds.refresh_token}")

if __name__ == "__main__":
    main()
