"""
auth.py — Google OAuth consent flow for Astroverse Auto-Shorts
==============================================================
Run this ONCE locally to create credentials/token.pickle with both
required scopes.  It does nothing else — no video building, no uploading,
no comment posting.

Usage:
    python auth.py

What it does:
    1. Opens a browser window for Google OAuth consent.
    2. Saves the resulting token to credentials/token.pickle.
    3. Prints the scopes that were granted and exits.

After running:
    • Re-encode the token for GitHub Actions:
        python -c "import base64, pathlib; print(base64.b64encode(pathlib.Path('credentials/token.pickle').read_bytes()).decode())"
    • Paste the output into your GitHub Actions secret (YT_TOKEN_B64).
"""

import pathlib
import pickle

from google_auth_oauthlib.flow import InstalledAppFlow

# ── Config — must match upload_youtube.py exactly ────────────────────────────
SCOPES  = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]
TOKEN   = "credentials/token.pickle"
SECRETS = "credentials/client_secret.json"
# ─────────────────────────────────────────────────────────────────────────────


def main() -> None:
    secrets_path = pathlib.Path(SECRETS)
    if not secrets_path.exists():
        raise FileNotFoundError(
            f"OAuth client secrets not found at '{SECRETS}'.\n"
            "Download it from Google Cloud Console → APIs & Services → Credentials."
        )

    print("Opening browser for Google OAuth consent …")
    print(f"Scopes requested:\n  " + "\n  ".join(SCOPES))
    print()

    flow  = InstalledAppFlow.from_client_secrets_file(str(secrets_path), SCOPES)
    creds = flow.run_local_server(port=0)

    token_path = pathlib.Path(TOKEN)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    with open(token_path, "wb") as f:
        pickle.dump(creds, f)

    print(f"\n✅  Token saved to '{TOKEN}'")
    print(f"    Scopes granted : {creds.scopes}")
    print(f"    Token expiry   : {creds.expiry}")
    print()
    print("Next step — encode for GitHub Actions secret:")
    print(
        "  python -c \""
        "import base64, pathlib; "
        f"print(base64.b64encode(pathlib.Path('{TOKEN}').read_bytes()).decode())"
        "\""
    )


if __name__ == "__main__":
    main()
