"""
refresh_ig_token.py — Refresh the long-lived Instagram access token.

Instagram-login tokens (IGAA…) last 60 days. Refreshing any time after the
token is 24 hours old resets the clock to a fresh 60 days. Run this locally
about once a month, then update the IG_ACCESS_TOKEN GitHub secret.

Usage:
    python refresh_ig_token.py

Reads the current token from credentials/ig_token.txt, refreshes it,
writes the new one back, and prints it for the GitHub secret update.
"""

import os
import pathlib
import requests

TOKEN_FILE = pathlib.Path("credentials/ig_token.txt")


def _update_supabase(new_token: str) -> bool:
    """Push the refreshed token to app_secrets so the reply-comments Edge
    Function (10-min auto-replies) keeps working. Reads Supabase creds from
    env or the webapp backend .env."""
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
    if not (url and key):
        return False
    r = requests.post(
        f"{url.rstrip('/')}/rest/v1/app_secrets",
        headers={"apikey": key, "Authorization": f"Bearer {key}",
                 "Content-Type": "application/json",
                 "Prefer": "resolution=merge-duplicates"},
        params={"on_conflict": "key"},
        json={"key": "ig_access_token", "value": new_token},
        timeout=30,
    )
    return r.status_code in (200, 201)


def main() -> None:
    token = TOKEN_FILE.read_text().strip()
    r = requests.get(
        "https://graph.instagram.com/refresh_access_token",
        params={"grant_type": "ig_refresh_token", "access_token": token},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()

    new_token  = data["access_token"]
    expires_in = data.get("expires_in", 0) // 86400   # seconds → days

    TOKEN_FILE.write_text(new_token)
    print(f"OK  Token refreshed — valid for {expires_in} days")
    print(f"    Saved to {TOKEN_FILE}")

    if _update_supabase(new_token):
        print("OK  Supabase app_secrets updated (10-min auto-replies keep working)")
    else:
        print("!!  Could not update Supabase app_secrets — update it manually")

    print()
    print("Update the GitHub secret IG_ACCESS_TOKEN with this value:")
    print(new_token)


if __name__ == "__main__":
    main()
