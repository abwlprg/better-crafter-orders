import os
import re
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
TOKEN_PATH = ROOT / ".gmail_refresh_token.txt"

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def load_env_file(path: Path) -> dict[str, str]:
    values = {}
    if not path.exists():
        return values

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def update_env_value(path: Path, key: str, value: str) -> None:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    pattern = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)

    replacement = f"{key}={value}"

    if pattern.search(text):
        text = pattern.sub(replacement, text)
    else:
        if text and not text.endswith("\n"):
            text += "\n"
        text += replacement + "\n"

    path.write_text(text, encoding="utf-8")


def main() -> None:
    env = load_env_file(ENV_PATH)

    client_id = os.getenv("GMAIL_CLIENT_ID") or env.get("GMAIL_CLIENT_ID")
    client_secret = os.getenv("GMAIL_CLIENT_SECRET") or env.get("GMAIL_CLIENT_SECRET")
    gmail_account = os.getenv("GMAIL_ACCOUNT") or env.get("GMAIL_ACCOUNT") or "bettercrafter1@gmail.com"

    if not client_id or not client_secret:
        raise SystemExit(
            "Missing Gmail OAuth credentials. Set GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET in .env first."
        )

    print("=" * 64)
    print("Gmail OAuth Setup — Better Crafter Orders")
    print("=" * 64)
    print(f"Sign in with: {gmail_account}")
    print("A browser window will open. Approve Gmail read-only access.")
    print("Do not paste the refresh token into chat, screenshots, docs, or Git.")
    print("=" * 64)

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)

    credentials = flow.run_local_server(
        port=0,
        prompt="consent",
        access_type="offline",
        authorization_prompt_message="Open this URL to authorize Gmail access:\n{url}\n",
        success_message="Gmail authorization complete. You can close this browser tab.",
        open_browser=True,
    )

    refresh_token = credentials.refresh_token

    if not refresh_token:
        raise SystemExit(
            "No refresh token was returned. Re-run the script and make sure you approve consent."
        )

    TOKEN_PATH.write_text(refresh_token + "\n", encoding="utf-8")
    update_env_value(ENV_PATH, "GMAIL_REFRESH_TOKEN", refresh_token)

    print()
    print("SUCCESS: Gmail refresh token was generated.")
    print(f"Saved full token to: {TOKEN_PATH.name}")
    print("Updated .env: GMAIL_REFRESH_TOKEN=<new token>")
    print()
    print("Security reminder:")
    print("- Do not commit .env")
    print("- Do not commit .gmail_refresh_token.txt")
    print("- Do not paste the token into chat, screenshots, docs, or logs")


if __name__ == "__main__":
    main()
