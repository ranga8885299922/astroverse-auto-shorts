"""
post_instagram.py — Auto-publish Reels via the Instagram API (Instagram login).

Uses the "Instagram API with Instagram Login" flow: a long-lived Instagram
token (starts with IGAA…) generated in the Meta app dashboard under
Use cases → API setup with Instagram login → Generate access tokens.
All calls go to graph.instagram.com and the token identifies the account,
so paths use /me/… .

The Reels API cannot accept a file upload — it needs a PUBLIC video URL.
We host each video temporarily in the Supabase Storage bucket 'shorts'
(public), publish the Reel from that URL, then delete the storage object.

Flow per video:
  1. Upload MP4 → Supabase Storage → public URL
  2. POST /me/media                  (create Reels container)
  3. Poll   /{container_id}?fields=status_code until FINISHED (~30-90 s)
  4. POST /me/media_publish
  5. DELETE the storage object

Config via env (all optional — everything degrades to a skip):
  SUPABASE_URL, SUPABASE_SERVICE_KEY   (storage hosting)
  IG_USER_ID                            Instagram professional account ID
                                        (informational; API uses /me)
  IG_ACCESS_TOKEN                       long-lived Instagram token (IGAA…),
                                        60-day expiry — refresh with
                                        refresh_ig_token.py

Rate limit: Instagram allows 25 API-published posts per 24 h — our 12/day fits.
"""

import os
import time
import pathlib
import datetime

import requests

IG_API = "https://graph.instagram.com/v21.0"

# ── Caption + first comment (edit here) ───────────────────────────────────────
IG_UTM = "utm_source=instagram&utm_medium=reels&utm_campaign=daily"
IG_CAPTION_TEMPLATE = (
    "{hook}\n\n"
    "{rasi} ఈరోజు రాశి ఫలాలు 🔮\n\n"
    "మీ పూర్తి వ్యక్తిగత జాతకం ఉచితంగా — bio లో లింక్ / astroloz.com\n\n"
    "#TeluguHoroscope #రాశిఫలాలు #DailyHoroscope #Astrology #{sign} "
    "#TeluguReels #Jyotishyam #astroloz"
)
# Posted as the Reel's first comment right after publish (like YouTube).
# Plain domain only — long URLs get auto-hidden as spam in comments.
IG_FIRST_COMMENT = (
    "🌟 మీ రాశి పూర్తి జాతకం, lucky time, remedies అన్నీ ఉచితంగా 👉 astroloz.com"
)
# ──────────────────────────────────────────────────────────────────────────────

PUBLISH_RETRIES = 1    # one automatic retry when a publish attempt fails
RETRY_WAIT      = 30   # seconds between attempts

STORAGE_BUCKET   = "shorts"
POLL_INTERVAL    = 10          # seconds between container status checks
POLL_MAX_TRIES   = 30          # 30 × 10 s = 5 min max wait per video


def instagram_enabled() -> bool:
    return bool(os.environ.get("IG_USER_ID") and os.environ.get("IG_ACCESS_TOKEN")
                and os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_KEY"))


def _storage_upload(video_path: str) -> tuple[str, str]:
    """Upload to Supabase Storage; returns (object_name, public_url)."""
    url = os.environ["SUPABASE_URL"].rstrip("/")
    key = os.environ["SUPABASE_SERVICE_KEY"]
    stamp = datetime.datetime.utcnow().strftime("%Y%m%d")
    name  = f"{stamp}/{pathlib.Path(video_path).name}"

    with open(video_path, "rb") as f:
        r = requests.post(
            f"{url}/storage/v1/object/{STORAGE_BUCKET}/{name}",
            headers={"Authorization": f"Bearer {key}",
                     "Content-Type": "video/mp4",
                     "x-upsert": "true"},
            data=f.read(),
            timeout=120,
        )
    r.raise_for_status()
    return name, f"{url}/storage/v1/object/public/{STORAGE_BUCKET}/{name}"


def _storage_delete(object_name: str) -> None:
    url = os.environ["SUPABASE_URL"].rstrip("/")
    key = os.environ["SUPABASE_SERVICE_KEY"]
    try:
        requests.delete(
            f"{url}/storage/v1/object/{STORAGE_BUCKET}/{object_name}",
            headers={"Authorization": f"Bearer {key}"},
            timeout=30,
        )
    except Exception:
        pass  # cleanup is best-effort; bucket is also cleared by date folders


def post_to_instagram(item: dict, video_path: str) -> str | None:
    """
    Publish one video as a Reel with automatic retry (transient container
    timeouts were causing occasional missing Reels). Returns the IG media id,
    or None on skip. Raises after all attempts fail.
    """
    if not instagram_enabled():
        return None

    last_err = None
    for attempt in range(PUBLISH_RETRIES + 1):
        try:
            return _publish_once(item, video_path)
        except Exception as e:
            last_err = e
            if attempt < PUBLISH_RETRIES:
                print(f"        ⚠ publish attempt {attempt+1} failed ({e}), "
                      f"retrying in {RETRY_WAIT}s...")
                time.sleep(RETRY_WAIT)
    raise last_err


def _publish_once(item: dict, video_path: str) -> str | None:
    token = os.environ["IG_ACCESS_TOKEN"]

    caption = IG_CAPTION_TEMPLATE.format(
        hook=" ".join((item.get("highlight_telugu") or "").split()),
        rasi=item.get("rasi_telugu", item.get("sign", "")),
        sign=item.get("sign", ""),
    )

    object_name, public_url = _storage_upload(video_path)
    try:
        # 1. Create Reels container (token identifies the account → /me)
        r = requests.post(
            f"{IG_API}/me/media",
            params={"media_type": "REELS",
                    "video_url":  public_url,
                    "caption":    caption,
                    "share_to_feed": "true",
                    "access_token": token},
            timeout=60,
        )
        r.raise_for_status()
        container = r.json()["id"]

        # 2. Wait for Instagram to fetch + process the video
        for _ in range(POLL_MAX_TRIES):
            time.sleep(POLL_INTERVAL)
            s = requests.get(
                f"{IG_API}/{container}",
                params={"fields": "status_code", "access_token": token},
                timeout=30,
            ).json()
            status = s.get("status_code")
            if status == "FINISHED":
                break
            if status == "ERROR":
                raise RuntimeError(f"IG container error: {s}")
        else:
            raise TimeoutError("IG container not ready after 5 min")

        # 3. Publish
        r = requests.post(
            f"{IG_API}/me/media_publish",
            params={"creation_id": container, "access_token": token},
            timeout=60,
        )
        r.raise_for_status()
        media_id = r.json().get("id")

        if media_id:
            # First comment with the astroloz.com link (like YouTube; non-fatal)
            try:
                requests.post(
                    f"{IG_API}/{media_id}/comments",
                    params={"message": IG_FIRST_COMMENT, "access_token": token},
                    timeout=30,
                )
            except Exception as e:
                print(f"        ⚠ first comment failed (non-fatal): {e}")

            # Log to Supabase for the performance feedback loop (non-fatal)
            from collect_insights import log_published
            log_published(media_id, item)
        return media_id

    finally:
        _storage_delete(object_name)
