"""
refresh_ig_token.py — Refresh the long-lived Instagram access tokens.

Instagram-login tokens (IGAA…) last 60 days. Refreshing any time after the
token is 24 hours old resets the clock to a fresh 60 days. Run this locally
about once a month.

Handles BOTH accounts:
  • astroloz_com   (Telugu) → credentials/ig_token.txt        → secret IG_ACCESS_TOKEN
  • astroloz.hindi (Hindi)  → credentials/ig_hindi_token.txt  → secret IG_HINDI_ACCESS_TOKEN

For each, it: refreshes the token, saves it back to its file, updates the
matching Supabase Vault/app_secrets key (so the 10-min reply Edge Function
keeps working), and prints the value to paste into the GitHub Actions secret.
An account is skipped cleanly if its token file is missing.

Usage:
    python refresh_ig_token.py
"""

import os
import pathlib
import requests

# (label, token file, Supabase app_secrets key, GitHub secret name)
ACCOUNTS = [
    ("astroloz_com (Telugu)",  "credentials/ig_token.txt",
     "ig_access_token",        "IG_ACCESS_TOKEN"),
    ("astroloz.hindi (Hindi)", "credentials/ig_hindi_token.txt",
     "ig_hindi_access_token",  "IG_HINDI_ACCESS_TOKEN"),
]


def _supabase_creds() -> tuple[str, str]:
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
    return url, key


def _update_supabase(secret_key: str, new_token: str) -> bool:
    url, key = _supabase_creds()
    if not (url and key):
        return False
    r = requests.post(
        f"{url.rstrip('/')}/rest/v1/app_secrets",
        headers={"apikey": key, "Authorization": f"Bearer {key}",
                 "Content-Type": "application/json",
                 "Prefer": "resolution=merge-duplicates"},
        params={"on_conflict": "key"},
        json={"key": secret_key, "value": new_token},
        timeout=30,
    )
    return r.status_code in (200, 201)


def _refresh_one(label, token_path, supabase_key, github_secret) -> None:
    p = pathlib.Path(token_path)
    if not p.exists():
        print(f"— {label}: no token file ({token_path}) — skipped\n")
        return

    try:
        r = requests.get(
            "https://graph.instagram.com/refresh_access_token",
            params={"grant_type": "ig_refresh_token",
                    "access_token": p.read_text().strip()},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"!! {label}: refresh FAILED ({e}) — token may already be expired; "
              f"regenerate it in the Meta dashboard\n")
        return

    new_token  = data["access_token"]
    expires_in = data.get("expires_in", 0) // 86400

    p.write_text(new_token)
    sb = "OK" if _update_supabase(supabase_key, new_token) else "FAILED (update manually)"
    print(f"✓ {label}")
    print(f"    valid {expires_in} days | saved to {token_path} | Supabase: {sb}")
    print(f"    → update GitHub secret {github_secret} with:")
    print(f"      {new_token}\n")


def main() -> None:
    for acct in ACCOUNTS:
        _refresh_one(*acct)
    print("Done. Update the printed GitHub secret(s) for accounts that refreshed.")


if __name__ == "__main__":
    main()
