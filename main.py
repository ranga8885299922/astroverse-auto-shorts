"""
Astroverse Auto-Shorts — Main Orchestrator
==========================================
Runs the full pipeline:
  1. Generate 72 scripts via Gemini
  2. For each script:
     a. Synthesise audio (Sarvam TTS)
     b. Build 9:16 video (MoviePy)
     c. Upload to YouTube
  3. Log every result to logs/run_log.csv
"""

import json
import pathlib
import csv
import datetime
import traceback
import os

from generate_script import generate_scripts
from tts_audio        import synthesize
from build_video      import build_video
from upload_youtube   import upload_video

OUT_DIR  = "output"
LOG_FILE = "logs/run_log.csv"

# ── Daily theme rotation (optional — overrides config.json if enabled) ────────
THEME_ROTATION = {
    0: "Monday motivation & new beginnings",
    1: "Love & relationships forecast",
    2: "Career & financial guidance",
    3: "Health & wellness energy",
    4: "Creativity & self-expression",
    5: "Weekend social energy",
    6: "Weekly overview & reflection",
}


def log_entry(row: dict):
    pathlib.Path("logs").mkdir(exist_ok=True)
    file_exists = pathlib.Path(LOG_FILE).exists()
    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=row.keys())
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def main():
    print("=" * 60)
    print("  🔮  ASTROVERSE AUTO-SHORTS")
    print(f"  Date : {datetime.date.today().isoformat()}")
    print("=" * 60)

    # Load config
    config = json.loads(pathlib.Path("config.json").read_text(encoding="utf-8"))

    # Optional: auto-rotate theme by weekday
    use_rotation = os.environ.get("USE_THEME_ROTATION", "true").lower() == "true"
    if use_rotation:
        weekday = datetime.date.today().weekday()
        config["daily_theme"] = THEME_ROTATION[weekday]
        print(f"  Theme : {config['daily_theme']}")

    # Ensure output folder exists
    pathlib.Path(OUT_DIR).mkdir(exist_ok=True)

    # ── Step 1: Generate scripts ──────────────────────────────────────────────
    print("\n[1/4] Generating scripts via Gemini...")
    items = generate_scripts(config)
    total = len(items)
    print(f"      ✓ {total} scripts ready\n")

    success_count = 0
    fail_count    = 0

    # ── Step 2-4: Process each item ───────────────────────────────────────────
    for i, item in enumerate(items, 1):
        sign = item["sign"]
        lang = item["language"]
        print(f"[{i:02d}/{total}]  {sign:14s} | {lang}")

        entry = {
            "date":      datetime.date.today().isoformat(),
            "run_id":    os.environ.get("GITHUB_RUN_ID", "local"),
            "sign":      sign,
            "language":  lang,
            "status":    "",
            "video_id":  "",
            "error":     "",
        }

        audio_path = None
        video_path = None

        try:
            # 2. TTS
            print(f"        → Sarvam TTS...")
            audio_path = synthesize(item, OUT_DIR)

            # 3. Build video
            print(f"        → MoviePy render...")
            video_path = build_video(item, audio_path, config, OUT_DIR)

            # 4. Upload
            print(f"        → YouTube upload...")
            vid_id = upload_video(item, video_path, config)

            entry["status"]  = "SUCCESS"
            entry["video_id"] = vid_id
            success_count += 1
            print(f"        ✓ https://youtube.com/shorts/{vid_id}")

        except Exception as e:
            entry["status"] = "FAILED"
            entry["error"]  = str(e)
            fail_count += 1
            print(f"        ✗ FAILED: {e}")
            traceback.print_exc()

        finally:
            # Clean up temp files regardless of success/failure
            for p in [audio_path, video_path]:
                if p and pathlib.Path(p).exists():
                    try:
                        os.remove(p)
                    except Exception:
                        pass

        log_entry(entry)

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print(f"  ✅  SUCCESS : {success_count}/{total}")
    print(f"  ❌  FAILED  : {fail_count}/{total}")
    print(f"  📄  Log     : {LOG_FILE}")
    print("=" * 60)

    if fail_count > 0:
        raise SystemExit(f"{fail_count} video(s) failed — check {LOG_FILE}")


if __name__ == "__main__":
    main()
