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

import pathlib
import requests

TOKEN_FILE = pathlib.Path("credentials/ig_token.txt")


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
    print()
    print("Update the GitHub secret IG_ACCESS_TOKEN with this value:")
    print(new_token)


if __name__ == "__main__":
    main()
