import os
import pickle
import pathlib

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ── Conversion CTA constants (edit here) ─────────────────────────────────────
UTM_CAMPAIGN  = "daily"          # change to "weekly" in the weekly repo
DESC_CTA_LINE = (
    "👉 మీ పూర్తి జాతకం ఉచితంగా: "
    f"https://astroloz.com/?utm_source=youtube&utm_medium=shorts&utm_campaign={UTM_CAMPAIGN}"
)
COMMENT_TEXT  = (
    "🌟 మీ రాశి పూర్తి జాతకం, lucky time, remedies అన్నీ ఉచితంగా "
    "👉 https://astroloz.com/?utm_source=youtube&utm_medium=shorts&utm_campaign=comment"
)
# ─────────────────────────────────────────────────────────────────────────────

# NOTE: youtube.force-ssl scope was added for commentThreads.insert.
# ⚠️  If your token.pickle was created with only youtube.upload you MUST
#     delete credentials/token.pickle and re-run locally once to re-authenticate
#     so the new token includes both scopes.
SCOPES  = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]
TOKEN   = "credentials/token.pickle"
SECRETS = "credentials/client_secret.json"


def get_youtube_client():
    """
    Handles OAuth2 token management.
    - First run (local): opens browser for user consent → saves token.pickle
    - Subsequent runs:   refreshes token automatically
    """
    creds = None

    if pathlib.Path(TOKEN).exists():
        with open(TOKEN, "rb") as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow  = InstalledAppFlow.from_client_secrets_file(SECRETS, SCOPES)
            creds = flow.run_local_server(port=0)

        pathlib.Path("credentials").mkdir(exist_ok=True)
        with open(TOKEN, "wb") as f:
            pickle.dump(creds, f)

    return build("youtube", "v3", credentials=creds)


def upload_video(item: dict, video_path: str, config: dict) -> str:
    """
    Uploads a single video to YouTube.
    Returns the YouTube video ID on success.
    """
    yt     = get_youtube_client()
    yt_cfg = config["youtube"]

    title = item.get("title_en", f'{item["sign"]} {item["language"]} Astrology #Shorts')
    # YouTube title limit is 100 chars
    title = title[:100]

    description = (
        f'{DESC_CTA_LINE}\n\n'
        f'🔮 {item["sign"]} | {item["language"]} Astrology Forecast\n\n'
        f'#{item["sign"]} #{item["language"]} #Astrology #DailyHoroscope #Shorts\n\n'
        f'🌐 Get your full personal horoscope free at astroloz.com'
    )

    tags = list(yt_cfg.get("tags", [])) + [item["sign"], item["language"], "Shorts"]

    body = {
        "snippet": {
            "title":       title,
            "description": description,
            "tags":        tags,
            "categoryId":  yt_cfg.get("category_id", "22"),
        },
        "status": {
            "privacyStatus":          yt_cfg.get("privacy", "public"),
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        video_path,
        mimetype  = "video/mp4",
        resumable = True,
        chunksize = 1024 * 1024,   # 1 MB chunks
    )

    request  = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None

    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            print(f"      Upload progress: {pct}%", end="\r")

    print()
    video_id = response["id"]

    # Post the channel CTA comment (non-fatal — won't fail the pipeline)
    try:
        post_comment(yt, video_id)
        print(f"      ✓ CTA comment posted")
    except Exception as e:
        print(f"      ⚠ Comment post failed (non-fatal): {e}")

    return video_id


def post_comment(yt, video_id: str) -> None:
    """Post the channel-owner CTA comment on the newly uploaded video."""
    yt.commentThreads().insert(
        part="snippet",
        body={
            "snippet": {
                "videoId": video_id,
                "topLevelComment": {
                    "snippet": {"textOriginal": COMMENT_TEXT}
                },
            }
        },
    ).execute()
