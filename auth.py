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

    print(f"\nOK  Token saved to '{TOKEN}'")
    print(f"    Scopes granted : {creds.scopes}")
    print(f"    Token expiry   : {creds.expiry}")

    # Sync the refresh token to Supabase app_secrets so the reply-comments
    # Edge Function (10-min YouTube auto-replies) keeps working after re-auth.
    try:
        import os, json, requests
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_SERVICE_KEY", "")
        if not (url and key):
            env_file = pathlib.Path(r"C:\Astroverse\Astroloz_webapp\astroloz-pwa\backend\.env")
            if env_file.exists():
                for line in env_file.read_text().splitlines():
                    if line.startswith("SUPABASE_URL="):
                        url = line.split("=", 1)[1].strip()
                    elif line.startswith("SUPABASE_SERVICE_KEY="):
                        key = line.split("=", 1)[1].strip()
        if url and key and creds.refresh_token:
            conf = json.loads(pathlib.Path(SECRETS).read_text())
            conf = conf.get("installed") or conf.get("web")
            for k, v in [("yt_client_id", conf["client_id"]),
                         ("yt_client_secret", conf["client_secret"]),
                         ("yt_refresh_token", creds.refresh_token)]:
                requests.post(
                    f"{url.rstrip('/')}/rest/v1/app_secrets",
                    headers={"apikey": key, "Authorization": f"Bearer {key}",
                             "Content-Type": "application/json",
                             "Prefer": "resolution=merge-duplicates"},
                    params={"on_conflict": "key"},
                    json={"key": k, "value": v}, timeout=30)
            print("OK  Supabase app_secrets synced (10-min YT replies keep working)")
        else:
            print("!!  Supabase not synced - update app_secrets yt_refresh_token manually")
    except Exception as e:
        print(f"!!  Supabase sync failed ({e}) - update app_secrets manually")
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
