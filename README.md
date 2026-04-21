# Astroverse Auto-Shorts

Automated pipeline to generate and upload 72 astrology YouTube Shorts per day.

## Stack
- **Gemini 1.5 Pro** — script generation
- **Sarvam AI (Bulbul v1)** — Telugu/Hindi/Tamil/Kannada/Bengali/Marathi TTS
- **MoviePy** — 9:16 video composition
- **YouTube Data API v3** — upload
- **GitHub Actions** — daily cron at 3:00 AM UTC (8:30 AM IST)

## Setup
See the full setup guide document for step-by-step instructions.

## Folder structure
```
astroverse-auto-shorts/
├── main.py
├── generate_script.py
├── tts_audio.py
├── build_video.py
├── upload_youtube.py
├── config.json
├── requirements.txt
├── backgrounds/          ← put your stars_loop.mp4 here
├── credentials/          ← client_secret.json + token.pickle
├── output/               ← temp folder (auto-cleaned)
├── logs/                 ← run_log.csv written here
└── .github/workflows/
    └── daily_shorts.yml
```

## Secrets required in GitHub
| Secret | Value |
|---|---|
| GEMINI_API_KEY | From Google AI Studio |
| SARVAM_API_KEY | From Sarvam dashboard |
| CLIENT_SECRET_JSON | Contents of credentials/client_secret.json |
| TOKEN_PICKLE_B64 | Base64-encoded credentials/token.pickle |
