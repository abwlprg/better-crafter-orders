"""
Setup Gmail Push Notifications via Google Pub/Sub.

Run this ONCE (and then every 7 days — it auto-renews via the /api/renew-watch endpoint).

Usage:
    python3 scripts/setup_gmail_watch.py

Requirements:
    - Pub/Sub topic already created: gmail-orders
    - gmail-api-push@system.gserviceaccount.com has Publisher role on the topic
    - GMAIL_REFRESH_TOKEN set in .env or environment
"""

import os
import sys
from pathlib import Path

# Load .env
env_file = Path(__file__).parent.parent / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

sys.path.insert(0, str(Path(__file__).parent.parent / "functions"))

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import config

GCP_PROJECT   = os.environ.get("GCP_PROJECT", "ordersbc-494213")
PUBSUB_TOPIC  = f"projects/{GCP_PROJECT}/topics/gmail-orders"
GMAIL_ACCOUNT = config.GMAIL_ACCOUNT  # bettercrafterorders@gmail.com

def get_gmail_service():
    creds = Credentials(
        token=None,
        refresh_token=os.environ["GMAIL_REFRESH_TOKEN"],
        token_uri=config.GMAIL_TOKEN_URI,
        client_id=os.environ.get("GMAIL_CLIENT_ID", config.GMAIL_CLIENT_ID),
        client_secret=os.environ.get("GMAIL_CLIENT_SECRET", config.GMAIL_CLIENT_SECRET),
        scopes=["https://www.googleapis.com/auth/gmail.readonly"],
    )
    creds.refresh(Request())
    return build("gmail", "v1", credentials=creds, cache_discovery=False)

if __name__ == "__main__":
    print(f"📬 Setting up Gmail push notifications...")
    print(f"   Account:     {GMAIL_ACCOUNT}")
    print(f"   Pub/Sub topic: {PUBSUB_TOPIC}")

    service = get_gmail_service()

    response = service.users().watch(
        userId=GMAIL_ACCOUNT,
        body={
            "topicName": PUBSUB_TOPIC,
            "labelIds": ["INBOX"],
            "labelFilterBehavior": "INCLUDE",
        }
    ).execute()

    print(f"\n✅ Watch activated!")
    print(f"   historyId:  {response.get('historyId')}")
    print(f"   expiration: {response.get('expiration')} (ms since epoch)")
    print(f"\n⚠️  This watch expires in 7 days.")
    print(f"   The system will auto-renew it via POST /api/renew-gmail-watch")
