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

from generate_script    import generate_scripts, generate_scripts_hindi
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

    # ── Instagram publishing pause switch (config.json) ───────────────────────
    # When false: NO Reels published, NO IG artifacts created, and Hindi (which
    # is Instagram-only) is skipped. YouTube is completely unaffected.
    ig_publish = config.get("instagram_publish_enabled", True)
    if not ig_publish:
        print("  Instagram publishing: PAUSED (flag off)")

    # Clear yesterday's videos so storage never fills up (mobile-friendly)
    print("\n  🧹 Clearing old videos from output/ and instagram/ ...")
    clear_dir(OUT_DIR)
    clear_dir(INSTA_DIR)

    # ── Step 0: Refresh performance metrics (data keeps accumulating) ─────────
    print("\n[0/4] Collecting Instagram insights from previous runs...")
    from collect_insights import collect, fetch_top_hooks
    try:
        collect()
    except Exception as e:
        print(f"      ⚠ insights collection failed (non-fatal): {e}")

    # Auto-reply to new comments (Instagram backstop + YouTube Shorts).
    # Instagram's primary replies run every 10 min via the Supabase Edge
    # Function; YouTube replies happen here nightly (needs OAuth creds).
    from reply_comments import reply_to_new_comments, reply_to_new_youtube_comments
    try:
        reply_to_new_comments()
    except Exception as e:
        print(f"      ⚠ IG comment auto-reply failed (non-fatal): {e}")
    try:
        reply_to_new_youtube_comments()
    except Exception as e:
        print(f"      ⚠ YT comment auto-reply failed (non-fatal): {e}")

    # Optional content steering — both OFF by default (pure AI content,
    # like the early well-performing version). Flip flags in config.json.
    top_hooks = None
    if config.get("use_hook_feedback", False):
        top_hooks = fetch_top_hooks()
        if top_hooks:
            print(f"      ✓ {len(top_hooks)} top hook(s) will steer today's scripts")

    grounding = None
    if config.get("use_bphs_grounding", False):
        print("\n[1/4] Fetching BPHS grounding from Supabase...")
        grounding = fetch_bphs_grounding(config["signs"])

    print("\n[1/4] Generating Telugu scripts via Groq...")
    items = generate_scripts(config, grounding, top_hooks)

    # ── Hindi (astroloz.hindi, Instagram only) — added as a second activity ──
    # Hindi has NO YouTube destination, so it is skipped whenever Instagram
    # publishing is paused.
    hindi_token = os.environ.get("IG_HINDI_ACCESS_TOKEN")
    if ig_publish and config.get("enable_hindi", True) and hindi_token:
        print("\n[1/4] Generating Hindi scripts via Groq...")
        try:
            items += generate_scripts_hindi(config)
        except Exception as e:
            print(f"      ⚠ Hindi generation failed (non-fatal): {e}")
    elif not ig_publish and config.get("enable_hindi", True):
        print("      (Hindi skipped — Instagram publishing paused; Hindi is Instagram-only)")
    elif config.get("enable_hindi", True):
        print("      (Hindi off — IG_HINDI_ACCESS_TOKEN not set)")

    total = len(items)
    print(f"      ✓ {total} scripts ready\n")

    success_count = 0
    fail_count    = 0
    ig_posted     = 0

    ig_on = ig_publish and instagram_enabled()
    if ig_publish and not instagram_enabled():
        print("      (Telugu IG auto-publish off — IG_ACCESS_TOKEN/SUPABASE_* not set)")

    # ── Step 2-4: Process each item — INSTAGRAM FIRST (primary target) ────────
    for i, item in enumerate(items, 1):
        sign = item["sign"]
        lang = item["language"]
        print(f"[{i:02d}/{total}]  {sign:14s} | {lang}")

        entry = {
            "date":        datetime.date.today().isoformat(),
            "run_id":      os.environ.get("GITHUB_RUN_ID", "local"),
            "sign":        sign,
            "language":    lang,
            "status":      "",
            "video_id":    "",
            "ig_media_id": "",
            "error":       "",
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

            is_hindi = item.get("lang") == "hi"

            # 4a. INSTAGRAM — optimise + publish. Fully gated by the pause flag:
            # when instagram_publish_enabled is false, NO IG artifact is created
            # and NO Instagram API call is made (no publish, no retry).
            if ig_publish:
                # Hindi → astroloz.hindi token; Telugu → default (env IG_ACCESS_TOKEN)
                ig_token = hindi_token if is_hindi else None
                ig_target_on = bool(ig_token) if is_hindi else ig_on
                insta_path = None
                try:
                    insta_path = optimize_for_instagram(video_path, INSTA_DIR)
                except Exception as e:
                    print(f"        ⚠ IG optimise failed (non-fatal): {e}")
                if ig_target_on and insta_path:
                    try:
                        acct = "astroloz.hindi" if is_hindi else "astroloz_com"
                        print(f"        → Instagram Reel → {acct}...")
                        media_id = post_to_instagram(item, insta_path, token=ig_token)
                        if media_id:
                            ig_posted += 1
                            entry["ig_media_id"] = media_id
                            print(f"        ✓ Reel published (media {media_id})")
                    except Exception as e:
                        entry["error"] += f"IG: {e}; "
                        print(f"        ⚠ Reel publish failed after retries: {e}")

            # 4b. YouTube — Telugu only (Hindi is Instagram-only)
            if is_hindi:
                entry["status"] = "SUCCESS"
                success_count += 1
                print(f"        ✓ Hindi Reel done (no YouTube)")
            else:
                print(f"        → YouTube upload...")
                vid_id = upload_video(item, video_path, config)
                entry["status"]  = "SUCCESS"
                entry["video_id"] = vid_id
                success_count += 1
                print(f"        ✓ https://youtube.com/shorts/{vid_id}")

        except Exception as e:
            entry["status"] = "FAILED"
            entry["error"] += str(e)
            fail_count += 1
            print(f"        ✗ FAILED: {e}")
            traceback.print_exc()

        finally:
            # Delete only the audio temp file. Videos stay for the artifact.
            if audio_path and pathlib.Path(audio_path).exists():
                try:
                    os.remove(audio_path)
                except Exception:
                    pass

        log_entry(entry)

    if ig_publish:
        print(f"\n      videos in '{INSTA_DIR}/' for download"
              + (f", {ig_posted} Reel(s) auto-published" if ig_on else ""))
    else:
        print("\n      Instagram publishing: PAUSED (flag off) — YouTube ran normally")

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
