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

# Per-sign search tags — Telugu transliteration + English, what people
# actually type into YouTube search.
SIGN_TAGS_EN = {
    "Aries":       ["mesha rasi",     "aries telugu"],
    "Taurus":      ["vrushabha rasi", "taurus telugu"],
    "Gemini":      ["mithuna rasi",   "gemini telugu"],
    "Cancer":      ["karkataka rasi", "cancer telugu"],
    "Leo":         ["simha rasi",     "leo telugu"],
    "Virgo":       ["kanya rasi",     "virgo telugu"],
    "Libra":       ["tula rasi",      "libra telugu"],
    "Scorpio":     ["vruschika rasi", "scorpio telugu"],
    "Sagittarius": ["dhanussu rasi",  "sagittarius telugu"],
    "Capricorn":   ["makara rasi",    "capricorn telugu"],
    "Aquarius":    ["kumbha rasi",    "aquarius telugu"],
    "Pisces":      ["meena rasi",     "pisces telugu"],
}

# Search-format tags added to every video
TREND_TAGS = ["today horoscope telugu", "daily rasi phalalu", "telugu astrology shorts"]

MAX_TAGS_CHARS = 470   # YouTube rejects uploads when total tag chars exceed 500

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

    # Telugu-first title (title_yt) gives better CTR than English-only.
    # Fall back to title_en then a generic title.
    title = item.get("title_yt") or item.get("title_en") \
        or f'{item["sign"]} {item["language"]} Astrology #Shorts'
    title = title[:100]  # YouTube hard limit

    rasi  = item.get("rasi_telugu", item["sign"])
    theme = config.get("daily_theme", "")
    hook  = " ".join(item.get("highlight_telugu", "").split())

    # Description SEO — first 2 lines (hook + link) are visible BEFORE
    # "show more", so the click-through link is always on screen.
    # Below the fold: covered-topics list, Telugu keyword paragraph, hashtags.
    description = (
        f'{hook}\n' if hook else ''
    ) + (
        f'{DESC_CTA_LINE}\n\n'
        f'🔮 {rasi} ఈరోజు రాశి ఫలాలు | {item["sign"]} Daily Telugu Horoscope\n\n'
        f'ఈ వీడియోలో: గ్రహ స్థితి ▸ కెరీర్ ▸ ధనం ▸ ప్రేమ & కుటుంబం ▸ '
        f'ఆరోగ్యం ▸ పరిహారం ▸ లక్కీ కలర్ & నంబర్\n\n'
        f'ఈరోజు {rasi} ఫలాలు: కెరీర్, ఉద్యోగం, వ్యాపారం, ధనం, ప్రేమ, వివాహం, '
        f'కుటుంబం, ఆరోగ్యం గురించి ఖచ్చితమైన వివరాలు. లక్కీ నంబర్, లక్కీ కలర్, '
        f'పరిహారం కూడా. మీ పూర్తి వ్యక్తిగత జాతకం ఉచితంగా astroloz.com లో.\n\n'
        f'#TeluguHoroscope #రాశిఫలాలు #Astrology #DailyHoroscope #{item["sign"]}\n\n'
        f'🌐 astroloz.com — మీ పూర్తి జాతకం ఉచితంగా'
    )

    # Tags: base (config) + per-sign search tags + date-format + daily theme.
    # Capped so total chars stay under YouTube's 500-char tag limit.
    tags, used = [], 0
    candidates = (
        list(yt_cfg.get("tags", []))
        + SIGN_TAGS_EN.get(item["sign"], [])
        + TREND_TAGS
        + [t for t in (theme, f'{rasi} ఫలాలు', f'{item["sign"]} horoscope today') if t]
        + [item["sign"], item["language"], "Shorts"]
    )
    for t in candidates:
        if t not in tags and used + len(t) <= MAX_TAGS_CHARS:
            tags.append(t)
            used += len(t)

    body = {
        "snippet": {
            "title":       title,
            "description": description,
            "tags":        tags,
            "categoryId":  yt_cfg.get("category_id", "22"),
            # Tell YouTube the content language — improves recommendation
            # targeting to Telugu-speaking viewers.
            "defaultLanguage":      "te",
            "defaultAudioLanguage": "te",
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
