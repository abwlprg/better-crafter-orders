"""Project-wide configuration constants for the automation workflow."""

from __future__ import annotations

STEPHEN_EMAIL: str = "7173783020@hellofax.com"
GMAIL_ACCOUNT: str = "bettercrafterorders@gmail.com"
FIRESTORE_COLLECTION: str = "processed_emails"
STORAGE_BUCKET: str | None = None
SEARCH_HOURS_BACK: int = 12

GMAIL_READONLY_SCOPE: str = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL_TOKEN_URI: str = "https://oauth2.googleapis.com/token"

GMAIL_CLIENT_ID: str = "706034452884-8u5fq9rsmb33o52ltj5qp4gnv668v2gl.apps.googleusercontent.com"
GMAIL_CLIENT_SECRET: str = "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"
GOOGLE_CREDENTIALS_JSON: str = "client_secret_706034452884-8u5fq9rsmb33o52ltj5qp4gnv668v2gl.apps.googleusercontent.com.json"

REPORT_PREFIX: str = "reports/stephen"
TEMPLATE_PATH: str = "templates/stephen_template.docx"
