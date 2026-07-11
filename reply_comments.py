"""
reply_comments.py — Auto-reply to new comments on our Reels.

Every pipeline run: list recent media → list their comments → reply to any
comment we haven't answered yet, pointing the commenter to astroloz.com.
Replied comment ids are stored in Supabase (`replied_comments`) so nobody
is ever replied to twice, even across runs.

Runs on the daily schedule, so replies arrive within ~24 h of the comment.
(Real-time replies would need webhooks + a published app — documented in
COPILOT.md as a future upgrade.)

Needs env: IG_ACCESS_TOKEN (with instagram_business_manage_comments),
SUPABASE_URL, SUPABASE_SERVICE_KEY. Skips silently when missing.
"""

import os
import datetime

import requests

IG_API = "https://graph.instagram.com/v21.0"

# ── Reply texts (edit here) ───────────────────────────────────────────────────
# The CTA promises "comment 'link' and I'll reply with the website link" —
# so the reply must contain the actual URL.
REPLY_TEXT = (
    "🌟 ఇదిగో మీ link 👉 "
    "https://astroloz.com/?utm_source=instagram&utm_medium=reels&utm_campaign=reply"
    " — మీ విద్య, ఉద్యోగం, వ్యాపారం, వివాహం ప్రశ్నలకు పూర్తి ఉచిత సమాధానాలు!"
)
YT_REPLY_TEXT = (
    "🌟 ఇదిగో మీ link 👉 "
    "https://astroloz.com/?utm_source=youtube&utm_medium=shorts&utm_campaign=reply"
    "\nమీ విద్య, ఉద్యోగం, వ్యాపారం, వివాహం ప్రశ్నలకు పూర్తి ఉచిత సమాధానాలు!"
)
# ──────────────────────────────────────────────────────────────────────────────

OWN_USERNAME       = "astroloz_com"   # never reply to our own comments
MEDIA_LOOKBACK     = 14               # days of media to scan
COMMENT_LOOKBACK   = 7                # only reply to comments this fresh
MAX_REPLIES_PER_RUN = 40              # safety valve against rate limits


def _env():
    return (
        os.environ.get("IG_ACCESS_TOKEN", ""),
        os.environ.get("SUPABASE_URL", "").rstrip("/"),
        os.environ.get("SUPABASE_SERVICE_KEY", ""),
    )


def _sb_headers(key: str) -> dict:
    return {"apikey": key, "Authorization": f"Bearer {key}",
            "Content-Type": "application/json"}


def _already_replied(url: str, key: str) -> set[str]:
    try:
        r = requests.get(
            f"{url}/rest/v1/replied_comments",
            headers=_sb_headers(key),
            params={"select": "comment_id", "limit": "10000"},
            timeout=30,
        )
        r.raise_for_status()
        return {row["comment_id"] for row in r.json()}
    except Exception:
        # If we can't read the dedupe table, replying is unsafe — do nothing.
        return None


def reply_to_new_comments() -> int:
    """Reply to unanswered comments on recent media. Returns replies sent."""
    token, url, key = _env()
    if not (token and url and key):
        print("      (comment auto-reply skipped — env not set)")
        return 0

    replied = _already_replied(url, key)
    if replied is None:
        print("      ⚠ comment auto-reply skipped — dedupe table unreachable")
        return 0

    now          = datetime.datetime.utcnow()
    media_since  = (now - datetime.timedelta(days=MEDIA_LOOKBACK)).strftime("%Y-%m-%dT%H:%M:%S")
    comment_since = (now - datetime.timedelta(days=COMMENT_LOOKBACK)).strftime("%Y-%m-%dT%H:%M:%S")

    try:
        media = requests.get(
            f"{IG_API}/me/media",
            params={"fields": "id,timestamp", "limit": "50",
                    "access_token": token},
            timeout=30,
        ).json().get("data", [])
    except Exception as e:
        print(f"      ⚠ comment scan failed (non-fatal): {e}")
        return 0

    sent = 0
    for m in media:
        if m.get("timestamp", "") < media_since:
            continue
        try:
            comments = requests.get(
                f"{IG_API}/{m['id']}/comments",
                params={"fields": "id,text,username,timestamp",
                        "limit": "50", "access_token": token},
                timeout=30,
            ).json().get("data", [])
        except Exception:
            continue

        for c in comments:
            if sent >= MAX_REPLIES_PER_RUN:
                break
            if (c["id"] in replied
                    or c.get("username") == OWN_USERNAME
                    or c.get("timestamp", "") < comment_since):
                continue
            try:
                r = requests.post(
                    f"{IG_API}/{c['id']}/replies",
                    params={"message": REPLY_TEXT, "access_token": token},
                    timeout=30,
                )
                r.raise_for_status()
                # Record BEFORE moving on so a crash can't cause double replies
                requests.post(
                    f"{url}/rest/v1/replied_comments",
                    headers={**_sb_headers(key),
                             "Prefer": "resolution=merge-duplicates"},
                    params={"on_conflict": "comment_id"},
                    json={"comment_id": c["id"], "media_id": m["id"],
                          "username": c.get("username"),
                          "comment_text": (c.get("text") or "")[:500]},
                    timeout=30,
                )
                sent += 1
            except Exception:
                continue

    print(f"      ✓ auto-replied to {sent} new comment(s)")
    return sent


def reply_to_new_youtube_comments() -> int:
    """
    Reply to unanswered comments on recent YouTube Shorts with the website
    link. Same dedupe table as Instagram (comment id formats never collide).
    Runs in the nightly pipeline (needs the OAuth token.pickle credentials).
    """
    _, url, key = _env()
    if not (url and key):
        print("      (YT comment auto-reply skipped — Supabase env not set)")
        return 0

    replied = _already_replied(url, key)
    if replied is None:
        print("      ⚠ YT comment auto-reply skipped — dedupe table unreachable")
        return 0

    try:
        from upload_youtube import get_youtube_client
        yt = get_youtube_client()
        ch = yt.channels().list(part="id,contentDetails", mine=True).execute()
        channel_id = ch["items"][0]["id"]
        uploads    = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    except Exception as e:
        print(f"      ⚠ YT comment scan failed (non-fatal): {e}")
        return 0

    now            = datetime.datetime.utcnow()
    video_cutoff   = (now - datetime.timedelta(days=MEDIA_LOOKBACK)).strftime("%Y-%m-%dT%H:%M:%SZ")
    comment_cutoff = (now - datetime.timedelta(days=COMMENT_LOOKBACK)).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        pl = yt.playlistItems().list(part="contentDetails",
                                     playlistId=uploads, maxResults=50).execute()
        video_ids = [it["contentDetails"]["videoId"] for it in pl.get("items", [])
                     if it["contentDetails"].get("videoPublishedAt", "") >= video_cutoff]
    except Exception as e:
        print(f"      ⚠ YT uploads list failed (non-fatal): {e}")
        return 0

    sent = 0
    for vid in video_ids:
        try:
            threads = yt.commentThreads().list(
                part="snippet", videoId=vid, maxResults=50,
                order="time", textFormat="plainText",
            ).execute()
        except Exception:
            continue  # comments disabled or not yet available

        for t in threads.get("items", []):
            if sent >= MAX_REPLIES_PER_RUN:
                break
            top = t["snippet"]["topLevelComment"]
            cid = top["id"]
            sn  = top["snippet"]
            author = (sn.get("authorChannelId") or {}).get("value", "")
            if (cid in replied
                    or author == channel_id
                    or sn.get("publishedAt", "") < comment_cutoff):
                continue
            try:
                yt.comments().insert(
                    part="snippet",
                    body={"snippet": {"parentId": cid,
                                      "textOriginal": YT_REPLY_TEXT}},
                ).execute()
                requests.post(
                    f"{url}/rest/v1/replied_comments",
                    headers={**_sb_headers(key),
                             "Prefer": "resolution=merge-duplicates"},
                    params={"on_conflict": "comment_id"},
                    json={"comment_id": cid, "media_id": vid,
                          "username": sn.get("authorDisplayName"),
                          "comment_text": (sn.get("textDisplay") or "")[:500]},
                    timeout=30,
                )
                sent += 1
            except Exception:
                continue

    print(f"      ✓ auto-replied to {sent} new YouTube comment(s)")
    return sent
