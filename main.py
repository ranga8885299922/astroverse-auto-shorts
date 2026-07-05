"""
Astroverse Auto-Shorts — Main Orchestrator
==========================================
Runs the full pipeline:
  1. Generate 12 scripts via Groq (llama-3.3-70b)
  2. For each script:
     a. Synthesise audio (gTTS)
     b. Build 9:16 video (MoviePy)
     c. Upload to YouTube
  3. Optimise all videos for Instagram → instagram/ folder (for offline download)
  4. Log every result to logs/run_log.csv

Storage note: output/ and instagram/ are CLEARED at the start of every run so
old videos never pile up on disk (important for mobile / limited storage).
"""

import json
import pathlib
import csv
import datetime
import traceback
import os
import shutil

from generate_script    import generate_scripts
from tts_audio          import synthesize
from build_video        import build_video
from upload_youtube     import upload_video
from optimize_instagram import optimize_for_instagram
from fetch_bphs         import fetch_bphs_grounding
from post_instagram     import post_to_instagram, instagram_enabled

OUT_DIR   = "output"      # YouTube-bound renders
INSTA_DIR = "instagram"   # Instagram-optimised copies (downloaded as artifact)
LOG_FILE  = "logs/run_log.csv"


def clear_dir(path: str):
    """Delete a folder and recreate it empty — clears yesterday's videos."""
    p = pathlib.Path(path)
    if p.exists():
        shutil.rmtree(p, ignore_errors=True)
    p.mkdir(parents=True, exist_ok=True)

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

    # Clear yesterday's videos so storage never fills up (mobile-friendly)
    print("\n  🧹 Clearing old videos from output/ and instagram/ ...")
    clear_dir(OUT_DIR)
    clear_dir(INSTA_DIR)

    # ── Step 0: Refresh performance metrics (feedback loop) ───────────────────
    print("\n[0/4] Collecting Instagram insights from previous runs...")
    from collect_insights import collect, fetch_top_hooks
    try:
        collect()
    except Exception as e:
        print(f"      ⚠ insights collection failed (non-fatal): {e}")

    # Auto-reply to new comments on recent Reels (CTA to astroloz.com)
    from reply_comments import reply_to_new_comments
    try:
        reply_to_new_comments()
    except Exception as e:
        print(f"      ⚠ comment auto-reply failed (non-fatal): {e}")
    top_hooks = fetch_top_hooks()
    if top_hooks:
        print(f"      ✓ {len(top_hooks)} top-performing hook(s) will steer today's scripts")

    # ── Step 1: Generate scripts (grounded in Parashara/BPHS rules DB) ────────
    print("\n[1/4] Fetching BPHS grounding from Supabase...")
    grounding = fetch_bphs_grounding(config["signs"])   # None → plain LLM mode

    print("\n[1/4] Generating scripts via Groq...")
    items = generate_scripts(config, grounding, top_hooks)
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
            print(f"        → gTTS audio...")
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
            # Delete only the audio temp file. KEEP the video — it is needed
            # for the Instagram optimisation / offline-download step below.
            if audio_path and pathlib.Path(audio_path).exists():
                try:
                    os.remove(audio_path)
                except Exception:
                    pass

        log_entry(entry)

    # ── Step 5: Optimise for Instagram + auto-publish Reels ───────────────────
    print("\n[+] Optimising videos for Instagram → instagram/ ...")
    slug_to_item = {
        f'{it["sign"]}_{it["language"]}'.replace(" ", "_").lower(): it
        for it in items
    }
    ig_on = instagram_enabled()
    if not ig_on:
        print("      (IG auto-publish off — IG_USER_ID/IG_ACCESS_TOKEN/SUPABASE_* not set)")

    insta_count = 0
    ig_posted   = 0
    for mp4 in sorted(pathlib.Path(OUT_DIR).glob("*.mp4")):
        try:
            out = optimize_for_instagram(str(mp4), INSTA_DIR)
            insta_count += 1
            print(f"      ✓ {pathlib.Path(out).name}")
        except Exception as e:
            print(f"      ⚠ Instagram optimise failed for {mp4.name}: {e}")
            continue

        if ig_on:
            item = slug_to_item.get(mp4.stem)
            if item:
                try:
                    media_id = post_to_instagram(item, out)
                    if media_id:
                        ig_posted += 1
                        print(f"        ✓ Reel published (media {media_id})")
                except Exception as e:
                    print(f"        ⚠ Reel publish failed (non-fatal): {e}")

    print(f"      {insta_count} video(s) ready in '{INSTA_DIR}/' for download"
          + (f", {ig_posted} Reel(s) auto-published" if ig_on else ""))

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
