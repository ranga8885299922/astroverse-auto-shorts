"""
collect_insights.py — Performance feedback loop for the shorts pipeline.

Two jobs:
  1. collect()        — pull view/reach/like counts for recently published
                        Reels from the Instagram API and upsert them into the
                        Supabase table `shorts_performance`.
  2. fetch_top_hooks() — return the hooks (highlight lines) of the best-
                        performing recent shorts, used to steer the next
                        day's script generation toward what actually works.

Needs env: IG_ACCESS_TOKEN, SUPABASE_URL, SUPABASE_SERVICE_KEY.
Everything degrades to a silent skip when config is missing — the pipeline
never breaks because of analytics.

Requires the instagram_business_manage_insights permission on the token.
"""

import os
import datetime

import requests

IG_API          = "https://graph.instagram.com/v21.0"
METRICS         = "views,reach,likes,comments,saved,shares"
LOOKBACK_DAYS   = 14   # only refresh metrics for media younger than this
TOP_HOOKS_LIMIT = 5


def _env():
    return (
        os.environ.get("IG_ACCESS_TOKEN", ""),
        os.environ.get("SUPABASE_URL", "").rstrip("/"),
        os.environ.get("SUPABASE_SERVICE_KEY", ""),
    )


def _sb_headers(key: str) -> dict:
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def log_published(media_id: str, item: dict) -> None:
    """Insert a row right after a Reel is published (metrics come later)."""
    _, url, key = _env()
    if not (url and key and media_id):
        return
    try:
        requests.post(
            f"{url}/rest/v1/shorts_performance",
            headers={**_sb_headers(key),
                     "Prefer": "resolution=merge-duplicates"},
            json={
                "platform":     "instagram",
                "media_id":     str(media_id),
                "sign":         item.get("sign"),
                "hook":         " ".join((item.get("highlight_telugu") or "").split()),
                "planet":       item.get("planet"),
                "theme":        item.get("theme"),
                "publish_date": datetime.date.today().isoformat(),
            },
            params={"on_conflict": "media_id"},
            timeout=30,
        )
    except Exception as e:
        print(f"      ⚠ perf log failed (non-fatal): {e}")


def collect() -> int:
    """Refresh metrics for recent media. Returns number of rows updated."""
    token, url, key = _env()
    if not (token and url and key):
        print("      (insights collection skipped — env not set)")
        return 0

    since = (datetime.datetime.utcnow()
             - datetime.timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%dT%H:%M:%S")

    try:
        media = requests.get(
            f"{IG_API}/me/media",
            params={"fields": "id,timestamp", "limit": "50",
                    "access_token": token},
            timeout=30,
        ).json().get("data", [])
    except Exception as e:
        print(f"      ⚠ insights media list failed (non-fatal): {e}")
        return 0

    updated = 0
    for m in media:
        if m.get("timestamp", "") < since:
            continue
        try:
            ins = requests.get(
                f"{IG_API}/{m['id']}/insights",
                params={"metric": METRICS, "access_token": token},
                timeout=30,
            ).json().get("data", [])
            values = {d["name"]: d["values"][0]["value"] for d in ins}
            if not values:
                continue

            requests.patch(
                f"{url}/rest/v1/shorts_performance",
                headers=_sb_headers(key),
                params={"media_id": f"eq.{m['id']}"},
                json={
                    "views":    values.get("views", 0),
                    "reach":    values.get("reach", 0),
                    "likes":    values.get("likes", 0),
                    "comments": values.get("comments", 0),
                    "saves":    values.get("saved", 0),
                    "shares":   values.get("shares", 0),
                    "fetched_at": datetime.datetime.utcnow().isoformat(),
                },
                timeout=30,
            )
            updated += 1
        except Exception:
            continue

    print(f"      ✓ insights refreshed for {updated} video(s)")
    return updated


def fetch_top_hooks(limit: int = TOP_HOOKS_LIMIT) -> list[str]:
    """Hooks of the most-viewed shorts in the lookback window (may be [])."""
    _, url, key = _env()
    if not (url and key):
        return []
    since = (datetime.date.today()
             - datetime.timedelta(days=LOOKBACK_DAYS)).isoformat()
    try:
        r = requests.get(
            f"{url}/rest/v1/shorts_performance",
            headers=_sb_headers(key),
            params={
                "select": "hook,views",
                "publish_date": f"gte.{since}",
                "hook": "neq.",
                "views": "gt.0",
                "order": "views.desc",
                "limit": str(limit),
            },
            timeout=30,
        )
        r.raise_for_status()
        return [row["hook"] for row in r.json() if row.get("hook")]
    except Exception:
        return []
