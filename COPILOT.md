# Astroverse Auto-Shorts — Growth Copilot

> Paste this file into any new Claude Code session working on this repo.
> It is the single source of truth for strategy, pipeline state, and roadmap.
> Update it whenever a phase ships or a decision changes.

---

## 1. Mission

Drive visitors to **astroloz.com** through free, algorithm-friendly short-form video.
Every Short / Reel is a funnel entry: watch → curiosity → click link in comment → sign up.

**Traffic equation:**
```
More languages × More platforms × Daily cadence × Strong CTA = Max visitors
```

---

## 2. Current Pipeline State

### Repos
| Repo | Purpose | Status |
|---|---|---|
| `astroverse-auto-shorts` (daily) | 12 Telugu signs × daily | ✅ Live |
| `astroverse-auto-shorts-weekly` | 12 Telugu signs × weekly recap | ✅ Live |

### Tech stack
- **Script**: Groq `llama-3.3-70b-versatile` → pure Telugu script
- **Voice**: gTTS `te` (Telugu)
- **Video**: MoviePy v2, 1080×1920, NotoSansTelugu-Bold font
- **Upload**: YouTube Data API v3 (OAuth2, token.pickle in GitHub secret `TOKEN_PICKLE_B64`)
- **Schedule**: cron-job.org → GitHub `workflow_dispatch` at 11:30 PM IST (6:00 PM UTC)
- **CTA**: Spoken at first sentence boundary + on-screen hook overlay 10–16 s
- **Auto-comment**: `commentThreads.insert` posts astroloz.com link after each upload

### CTA strings (current — edit in constants at top of each file)
| Location | String |
|---|---|
| `generate_script.py CTA_SPOKEN` | "మీ personal జాతకం astroloz dot com లో completely free. లింక్ కింద కామెంట్‌లో ఉంది." |
| `build_video.py CTA_SCREEN_TEL1` | "మీ personal జాతకం" |
| `build_video.py CTA_SCREEN_LATIN` | "astroloz.com - completely free" |
| `build_video.py CTA_SCREEN_TEL2` | "లింక్ కింద కామెంట్‌లో ఉంది" |
| `upload_youtube.py COMMENT_TEXT` | Full URL with `utm_campaign=comment` |
| `upload_youtube.py UTM_CAMPAIGN` | `"daily"` (change to `"weekly"` in weekly repo) |

### Known font rules (do not break these)
- Telugu text → always `NotoSansTelugu-Bold` (`tel_bold`)
- Latin text (URLs, English words) → always `FONT_BOLD` (Arial/DejaVu)
- Never mix both scripts in a single `TextClip` — NotoSansTelugu has no Latin glyphs, mixing renders boxes

---

## 3. YouTube Views Growth Plan (Telugu — active)

### Phase A — Foundation (now)
- [x] Daily 12 videos auto-uploaded
- [x] Weekly 12 recap videos
- [x] Spoken CTA at hook (~10 s)
- [x] On-screen overlay 10–16 s
- [x] Auto first-comment with astroloz.com link
- [x] UTM tracking: `utm_source=youtube&utm_medium=shorts&utm_campaign=daily`

### Phase B — Optimise for algorithm (next 30 days)
These are code changes — implement one at a time, test with one sign first.

**SHIPPED 2026-06-21:**
- [x] **Hook line = title** — `build_title()` in `generate_script.py`: `"{highlight} | {rasi} ఫలాలు {date}"`, highlight truncated to keep total ≤100 chars. Thumbnail text and title now say the same thing (B1 superseded).
- [x] **Specific predictions** — Groq prompt now enforces concrete details per category (body part for health, money source, work situation, family member, deity+day for remedy); temperature 0.7→0.85 for daily variety
- [x] **Audio hook first** — script_telugu must START with the curiosity hook, no greeting; spoken CTA moved to after the SECOND sentence so it still lands ~10s (aligned with 10–16s overlay)
- [x] **Description SEO v2** — hook + link above the fold, covered-topics list, Telugu keyword paragraph, 5 hashtags
- [x] **Tag engine** — per-sign transliteration tags (SIGN_TAGS_EN), trending-format tags, dedup + 470-char cap (YouTube limit 500)
- [x] **defaultLanguage/defaultAudioLanguage = "te"** — better recommendation targeting
- [x] **config.json cleanup** — removed dead promo_* keys (code no longer reads them)

**SHIPPED 2026-06-14 (commit pending):**
- [x] **Telugu-first title** with curiosity hook — `TITLE_TEMPLATE` in `generate_script.py`
      → `"{rasi}: ఈరోజు ఏం జరగబోతుంది? {date} 🔮 రాశి ఫలాలు #shorts"` (was English-only, killing CTR)
- [x] **Dramatic thumbnail highlight** — tightened Groq prompt (no hedging, max 8 words, present tense)
- [x] **Daily + Telugu tags** — `upload_youtube.py` appends theme + `{rasi} ఫలాలు` + sign tags
- [x] **Keyword-rich Telugu description** — full Telugu keyword block for search indexing

**B1 — Title A/B rotation**
YouTube's algorithm favours CTR. Rotate 3 title templates per sign daily:
```python
TITLE_TEMPLATES = [
    "{sign} రాశి ఫలాలు {date} | {highlight}",
    "ఈరోజు {sign} రాశి వారికి ఏం జరగబోతుందో చూడండి",
    "{sign} horoscope {date} | Telugu astrology",
]
# Pick by: hash(sign + date) % 3 → deterministic but rotates daily
```
File to edit: `generate_script.py` → `title_en` field (or post-process in `upload_youtube.py`).

**B2 — Thumbnail hook (first 5 seconds)**
The highlight card (0–5 s) is the thumbnail. Make `highlight_telugu` more dramatic.
Add to the Groq prompt: *"highlight_telugu must be a shocking or exciting prediction, max 8 words, present tense, no hedging words like 'might' or 'possible'."*

**B3 — Tag expansion**
Current tags are static. Add sign-specific + theme-specific tags each day.
In `upload_youtube.py`, append to `tags`:
```python
daily_tags = [config["daily_theme"], f"{item['sign']} {date_str}", "shorts 2026"]
tags = base_tags + daily_tags + [item["sign"], item["language"], "Shorts"]
```

**B4 — Chapters / description structure**
YouTube search indexes description text. Improve description format:
```
Line 1: CTA with UTM link (already done)
Line 2: blank
Line 3: 00:00 Highlight | 00:05 Career | 00:20 Love | 00:35 Health | 00:50 Lucky
Line 4: hashtags
Line 5: astroloz.com tagline
```
The timestamps improve watch time by letting viewers scrub to their interest.

**B5 — Playlist auto-assignment**
Group all 12 daily signs into a dated playlist (e.g. "Daily Horoscope Jun 11 2026").
YouTube surfaces playlists in search and suggested. Use `playlistItems.insert` after upload.
Needs `youtube` scope (already have it via `force-ssl`).

### Phase C — Scale Telugu (60–90 days)
- Run daily + weekly on separate channels (more upload slots, less spam risk per channel)
- Add monthly "Varshaphal" (annual horoscope) long-form video per sign — these rank in search
- Experiment with 2× daily uploads: morning preview (30 s) + evening full (60 s)

---

## 4. Multi-Language Channel Plan

Languages already configured in `config.json` under `_languages_paused` — fonts are ready.
Activation order based on speaker population × astrology search volume:

| Priority | Language | Code | Font | YouTube market | Est. activate |
|---|---|---|---|---|---|
| 1 | **Hindi** | `hi-IN` | Noto Sans Devanagari | 500 M speakers, huge astrology search | Month 2 |
| 2 | **Tamil** | `ta-IN` | Noto Sans Tamil | 80 M, strong devotional content culture | Month 2 |
| 3 | **Kannada** | `kn-IN` | Noto Sans Kannada | 45 M, underserved on YouTube | Month 3 |
| 4 | **Bengali** | `bn-IN` | Noto Sans Bengali | 230 M, growing Shorts audience | Month 3 |
| 5 | **Marathi** | `mr-IN` | Noto Sans Devanagari | 80 M, high engagement | Month 4 |

### How to activate a language (checklist)
1. In `config.json`: move language entry from `_languages_paused` → `languages` array
2. Create a new YouTube channel for that language (separate channel = separate algorithm, less spam flag risk)
3. Run `auth.py` for that channel's Google account → new `token.pickle`
4. Fork the daily repo → update `UTM_CAMPAIGN`, TTS lang map, font path, YouTube secret
5. Update `CTA_SPOKEN` and overlay strings to that language
6. Test render one sign before enabling GitHub Actions schedule
7. Set up cron-job.org trigger for that repo

### Per-language CTA strings to write (do this before activating)
| Language | Spoken CTA template | Screen line 2 |
|---|---|---|
| Hindi | "आपकी personal कुंडली astroloz dot com पर completely free. Link नीचे comment में है." | "link comment में है" |
| Tamil | "உங்கள் personal ஜாதகம் astroloz dot com-ல் completely free. Link கீழே comment-ல் உள்ளது." | "link comment-ல் உள்ளது" |
| Kannada | "ನಿಮ್ಮ personal ಜಾತಕ astroloz dot com ನಲ್ಲಿ completely free. Link ಕೆಳಗೆ comment ನಲ್ಲಿದೆ." | "link comment ನಲ್ಲಿದೆ" |

---

## 4.5. Offline / Instagram download (SHIPPED 2026-06-14)

The pipeline runs in GitHub Actions (cloud), usually triggered from mobile.
Videos can't land on the phone automatically, so:

- `main.py` clears `output/` and `instagram/` at the **start** of every run
  (old videos never pile up — important for limited mobile/PC storage).
- Videos are **kept** after YouTube upload (no longer deleted).
- `optimize_instagram.py` makes a `+faststart` Instagram-ready copy of each
  video into `instagram/` (lossless stream-copy; falls back to plain copy if
  ffmpeg is missing locally). Source is already 1080×1920 H.264/AAC/30fps =
  Reels spec, so no re-encode needed.
- Workflow uploads `instagram/*.mp4` as artifact **instagram-shorts-<run_id>**
  (retention 7 days). **Download on mobile:** GitHub mobile site → the run →
  Artifacts → instagram-shorts → unzip → share each to Instagram.

**Upgrade path (better mobile UX, needs 1 secret):** Telegram bot delivery —
add `post_telegram.py` that sends each `instagram/*.mp4` to a chat via bot
token. Videos arrive in Telegram, tap to save → share to Instagram. No zip.

## 5. Instagram Reels Plan — DIRECT auto-post (activate when YouTube Telugu hits ~5K subscribers)

### Why wait
Instagram Reels require a Creator/Business account connected to a Facebook Page.
The Meta Content Publishing API has rate limits (25 posts/day per account).
The Reels format is identical (1080×1920) — the same MP4 file works directly.

### Architecture (when ready)
Add `post_instagram.py` alongside `upload_youtube.py` — same pipeline, new destination.

```
main.py
  └── generate_script.py   (unchanged)
  └── tts_audio.py         (unchanged)
  └── build_video.py       (unchanged — same 1080×1920 MP4)
  └── upload_youtube.py    (unchanged)
  └── post_instagram.py    (NEW — Meta Graph API)
```

**`post_instagram.py` skeleton (do not implement yet — save for Phase C):**
```python
# Requires: pip install requests
# Requires env vars: IG_USER_ID, IG_ACCESS_TOKEN (long-lived token, 60-day expiry)
# Scope needed: instagram_content_publish, instagram_basic

import os, requests, time

IG_BASE    = "https://graph.facebook.com/v19.0"
IG_USER_ID = os.environ["IG_USER_ID"]
IG_TOKEN   = os.environ["IG_ACCESS_TOKEN"]

# UTM for Instagram traffic
IG_UTM = "utm_source=instagram&utm_medium=reels&utm_campaign=daily"
IG_CAPTION_TEMPLATE = (
    "{rasi} రాశి ఫలాలు {date}\n\n"
    "{highlight}\n\n"
    "మీ personal జాతకం completely free\n"
    "astroloz.com/?{utm}\n\n"
    "#horoscope #telugu #{sign} #astrology #shorts #reels"
)

def post_reel(video_url, caption, cover_url=None):
    # Step 1: Create media container
    r = requests.post(f"{IG_BASE}/{IG_USER_ID}/media", params={
        "media_type": "REELS",
        "video_url":  video_url,   # must be a public URL — upload to S3/GCS first
        "caption":    caption,
        "access_token": IG_TOKEN,
    })
    container_id = r.json()["id"]

    # Step 2: Poll until ready (video processing takes 30–90 s)
    for _ in range(20):
        time.sleep(10)
        status = requests.get(f"{IG_BASE}/{container_id}", params={
            "fields": "status_code", "access_token": IG_TOKEN
        }).json()
        if status["status_code"] == "FINISHED":
            break

    # Step 3: Publish
    requests.post(f"{IG_BASE}/{IG_USER_ID}/media_publish", params={
        "creation_id": container_id,
        "access_token": IG_TOKEN,
    })
```

**Key Instagram differences vs YouTube:**
| Concern | YouTube | Instagram |
|---|---|---|
| File delivery | Upload binary via resumable API | Must be a **public URL** (S3/GCS/CDN) |
| Token refresh | Long-lived via `refresh_token` | 60-day long-lived token, must re-auth manually or automate refresh |
| Rate limit | Per-video quota | 25 container creates / 24 h per account |
| Caption link | Description + comment | Caption only (no clickable link in caption on feed) — use link-in-bio |
| Analytics UTM | `utm_medium=shorts` | `utm_medium=reels` |

**Instagram link-in-bio strategy:**
Since Instagram doesn't make caption links clickable, use a link-in-bio tool (e.g. Linktree or a custom `/link` page on astroloz.com) that routes to the sign-specific horoscope page.
Best approach: `astroloz.com/r/{sign}` → redirects to full horoscope. Trackable per-sign.

---

## 6. Full UTM Tracking Map

All traffic to astroloz.com should be trackable by source:

| Source | Medium | Campaign | Where set |
|---|---|---|---|
| YouTube Shorts daily | shorts | daily | `upload_youtube.py UTM_CAMPAIGN` |
| YouTube Shorts weekly | shorts | weekly | weekly repo `UTM_CAMPAIGN` |
| YouTube auto-comment | shorts | comment | `upload_youtube.py COMMENT_TEXT` |
| Instagram Reels | reels | daily | `post_instagram.py IG_UTM` |
| Instagram bio link | reels | bio | Static link-in-bio page |

In Google Analytics / Mixpanel on astroloz.com, create a **Shorts Funnel** report:
```
Event: session_start (utm_source=youtube OR instagram)
  → Event: page_view /horoscope/*
    → Event: sign_up OR free_reading_start
```
This shows conversion rate from each Short to actual product engagement.

---

## 7. Content Calendar & Theme Rotation

`main.py` already rotates daily themes by weekday:

| Day | Theme |
|---|---|
| Monday | Monday motivation & new beginnings |
| Tuesday | Love & relationships forecast |
| Wednesday | Career & financial guidance |
| Thursday | Health & wellness energy |
| Friday | Creativity & self-expression |
| Saturday | Weekend social energy |
| Sunday | Weekly overview & reflection |

**Recommended additions (edit `THEME_ROTATION` in `main.py`):**
- Festival days: override theme to "Diwali special", "Ugadi predictions", etc.
- Eclipse / planetary event days: "Lunar eclipse effect on your sign"
- Monthly: first day of each month → "Monthly forecast {sign}"

---

## 8. Operational Runbook

### Daily check (2 min)
1. Check cron-job.org dashboard → last run status
2. Check GitHub Actions → latest run → confirm 12 SUCCESS in log
3. Spot-check 1 video on YouTube → confirm comment posted

### Weekly check (15 min)
1. Review `logs/run_log.csv` artifacts → any FAILED rows?
2. Check YouTube Studio analytics → which signs get highest views, CTR, watch time
3. Check astroloz.com analytics → `utm_campaign=daily` sessions this week vs last week

### When the pipeline breaks
| Symptom | Likely cause | Fix |
|---|---|---|
| All 12 FAILED: `KeyError youtube` | `config.json` missing `youtube` block | Add the block (see config.json) |
| All 12 FAILED: `401 Unauthorized` | `token.pickle` expired or wrong scope | Run `auth.py` locally → update `TOKEN_PICKLE_B64` secret |
| Scheduled run skipped | GitHub Actions queue congestion | Use cron-job.org → `workflow_dispatch` instead |
| Telugu text shows boxes | Wrong font in TextClip | Check `tel_bold` = `TELUGU_BOLD_PATH`; never mix Latin+Telugu in one clip |
| Audio CTA cuts mid-word | Sentence boundary not found | Check `CTA_SPOKEN` string ends with `.` or `।` so boundary is detected |
| gTTS rate limit | Too many requests | Add `time.sleep(2)` between signs in `generate_scripts()` |

### Re-auth procedure (when token expires)
```powershell
# 1. Delete old token
Remove-Item credentials\token.pickle

# 2. Re-auth (browser opens)
python auth.py

# 3. Encode for GitHub
[Convert]::ToBase64String([IO.File]::ReadAllBytes("$PWD\credentials\token.pickle")) | Set-Content token_b64.txt
# Open token_b64.txt → copy → paste into GitHub secret TOKEN_PICKLE_B64
Remove-Item token_b64.txt
```

---

## 9. Prioritised Backlog

| # | Item | Impact | Effort | Phase |
|---|---|---|---|---|
| 1 | Playlist auto-assignment per day | Medium | Low | B |
| 2 | Title A/B rotation | High | Low | B |
| 3 | Activate Hindi channel | Very High | Medium | C |
| 4 | Activate Tamil channel | High | Medium | C |
| 5 | Tag expansion with daily theme | Medium | Low | B |
| 6 | Description chapters / timestamps | Medium | Low | B |
| 7 | Monthly Varshaphal long-form video | High | High | C |
| 8 | Instagram Reels pipeline | Very High | High | D |
| 9 | Activate Kannada / Bengali / Marathi | High | Medium | D |
| 10 | astroloz.com `/r/{sign}` redirect page | Medium | Low | C |
| 11 | Per-sign performance dashboard | Medium | Medium | D |

---

## 10. File Map (quick reference)

```
astroverse-auto-shorts/
├── main.py                  # orchestrator — runs full pipeline
├── generate_script.py       # Groq LLM → Telugu script + CTA_SPOKEN insert
├── tts_audio.py             # gTTS → mp3/wav audio
├── build_video.py           # MoviePy → 1080×1920 mp4 with overlays
├── upload_youtube.py        # YouTube Data API v3 upload + auto-comment
├── auth.py                  # run once locally to re-auth OAuth token
├── optimize_instagram.py    # makes Instagram-ready (+faststart) copies into instagram/
├── test_render.py           # render ONE sign locally, no upload
├── config.json              # all editable strings, tags, sign list, languages
├── fonts/                   # NotoSansTelugu-Regular.ttf + Bold (auto-downloaded)
├── credentials/             # client_secret.json + token.pickle (gitignored)
├── logs/run_log.csv         # per-run success/fail log
└── .github/workflows/
    └── daily_shorts.yml     # GitHub Actions — triggered by cron-job.org
```
