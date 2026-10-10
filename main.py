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


def _is_youtube_cap(exc) -> bool:
    """True when a YouTube upload failed because the channel hit its daily
    upload limit (uploadLimitExceeded).

    This is an external account cap, not a pipeline fault: the Instagram Reel
    for the sign still published, and the only reason uploads overflow is the
    lowered daily limit after the channel lost 'advanced features'. We treat it
    as a deferred item (not a failure) so the run stays green and stops firing
    'all jobs failed' alerts every night. The real fix is to raise the cap by
    verifying the channel at youtube.com/verify."""
    s = str(exc)
    return "uploadLimitExceeded" in s or "exceeded the number of videos" in s


def main():
    print("=" * 60)
    print("  🔮  ASTROVERSE AUTO-SHORTS")
    print(f"  Date : {datetime.date.today().isoformat()}")
    print("=" * 60)

    # Load config
    config = json.loads(pathlib.Path("config.json").read_text(encoding="utf-8"))

    # Keep Supabase app_secrets in sync with the live IG tokens so the 10-min
    # reply-comments Edge Function always replies with a valid token (it reads
    # the token from app_secrets, not the GitHub secret). Runs every pipeline run.
    from post_instagram import sync_tokens_to_supabase
    print("\n  🔑 Syncing IG tokens → Supabase app_secrets (for comment replies)...")
    sync_tokens_to_supabase()

    # Sync-only mode: a manual run that ONLY refreshes app_secrets and exits —
    # fixes IG replies immediately after a token rotation, without regenerating
    # or re-posting today's videos.
    if os.environ.get("SYNC_SECRETS_ONLY", "").strip().lower() == "true":
        print("  SYNC_SECRETS_ONLY set — app_secrets refreshed, exiting without a run.")
        return

    # Verify-only mode: confirm which LLM provider/model is active and that it
    # generates cleanly in CI (e.g. after adding the GEMINI_API_KEY secret), then
    # exit without rendering or posting anything.
    if os.environ.get("VERIFY_LLM", "").strip().lower() == "true":
        from generate_script import _provider_chain
        from tts_audio import _duration, _bundled_ffmpeg   # synthesize is imported at module top
        _chain = _provider_chain()
        print("\n  [VERIFY] LLM chain: " + " -> ".join(f"{n}({m})" for n, _c, m in _chain))
        vcfg = dict(config); vcfg["signs"] = ["Aries", "Leo"]
        vitems = generate_scripts(vcfg, None, None)
        ff = _bundled_ffmpeg()
        pathlib.Path("output").mkdir(exist_ok=True)
        for o in vitems:
            ap = synthesize(o, "output")
            d = _duration(ff, ap) if ff else -1.0
            print(f"  [VERIFY] {o['sign']}: words={len(o['script'].split())} dur={d:.1f}s under90={d < 90}")
            print(f"  [VERIFY] sample: {o['script'][:90]}")
        print("  [VERIFY] OK — model generates cleanly. Exiting without posting.")
        return

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

    # ── YouTube publishing switch (env, set by the workflow input) ────────────
    # Default true. A manual "Instagram-only" run passes youtube_enabled=false,
    # so we render + post the Telugu Reels but skip the YouTube upload. Scheduled
    # runs never set it, so YouTube uploads as normal.
    yt_publish = os.environ.get("YOUTUBE_PUBLISH_ENABLED", "true").strip().lower() != "false"
    if not yt_publish:
        print("  YouTube publishing: SKIPPED (Instagram-only run)")

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
    # Hindi has NO YouTube destination. It is gated by its own enable_hindi flag
    # (astroloz.hindi was flagged for unoriginal content 2026-08 → paused there)
    # AND by the global instagram_publish_enabled kill-switch. Telugu is separate.
    hindi_token = os.environ.get("IG_HINDI_ACCESS_TOKEN")
    hindi_wanted = config.get("enable_hindi", True)
    if not hindi_wanted:
        print("      Hindi channel (astroloz.hindi): PAUSED (enable_hindi off)")
    elif not ig_publish:
        print("      (Hindi skipped — Instagram publishing paused; Hindi is Instagram-only)")
    elif not hindi_token:
        print("      (Hindi off — IG_HINDI_ACCESS_TOKEN not set)")
    else:
        print("\n[1/4] Generating Hindi scripts via Groq...")
        try:
            items += generate_scripts_hindi(config)
        except Exception as e:
            print(f"      ⚠ Hindi generation failed (non-fatal): {e}")

    total = len(items)
    print(f"      ✓ {total} scripts ready\n")

    success_count = 0
    fail_count    = 0
    ig_posted     = 0
    yt_uploaded   = 0       # successful YouTube uploads this run
    ig_only       = 0       # Telugu items published to IG but intentionally not to YouTube
    yt_capped     = 0       # items where YouTube's daily upload cap was hit (IG still published)
    yt_cap_hit    = False   # once the cap is reached, skip the remaining YouTube attempts

    # YouTube is capped at a daily upload limit while the channel is unverified,
    # so we only send the best-performing rashis there; every sign still goes to
    # Instagram. youtube_signs is the allow-list (empty = all signs); the integer
    # youtube_max_uploads is a hard safety cap enforced regardless of the list.
    yt_signs = set(config.get("youtube_signs") or [])          # empty set = all allowed
    yt_max   = int(config.get("youtube_max_uploads", 0) or 0)  # 0 = no cap
    if yt_publish and yt_signs:
        print(f"  YouTube: top {len(yt_signs)} rashis only (cap {yt_max or 'none'}); others are Instagram-only")

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

            # 3. Build video — recorded deity+emblem scene when use_scene_video
            # is on; MoviePy caption render otherwise. Scene failures fall back
            # to MoviePy so a run never dies on the recorder.
            if config.get("use_scene_video", False):
                try:
                    from record_scene import build_scene_video
                    print(f"        → recording deity scene...")
                    video_path = build_scene_video(item, audio_path, config, OUT_DIR)
                except Exception as e:
                    print(f"        ⚠ scene record failed ({e}) — MoviePy fallback")
                    traceback.print_exc()
                    video_path = build_video(item, audio_path, config, OUT_DIR)
            else:
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
            elif not yt_publish:
                entry["status"] = "SUCCESS"
                success_count += 1
                print(f"        ✓ Telugu Reel done (YouTube skipped — Instagram-only run)")
            elif yt_signs and sign not in yt_signs:
                # Not in the YouTube top-rashis allow-list — Instagram only. The
                # IG Reel already published above, so this is a success, not a
                # skip-failure: the lower-performing rashis stay off YouTube to
                # keep uploads under its daily cap.
                entry["status"] = "IG_ONLY"
                success_count += 1
                ig_only += 1
                print(f"        – YouTube skipped (not in top-{len(yt_signs)} YouTube rashis) — IG Reel live")
            elif yt_max and yt_uploaded >= yt_max:
                # Hard safety cap already reached this run — IG only from here.
                entry["status"] = "IG_ONLY"
                success_count += 1
                ig_only += 1
                print(f"        – YouTube skipped (daily cap {yt_max} reached) — IG Reel live")
            elif yt_cap_hit:
                # YouTube daily cap already reported by the API earlier this run —
                # it would just 400 again. Skip the call; IG Reel is already live.
                entry["status"] = "YT_CAPPED"
                entry["error"] += "YouTube daily upload cap reached (uploadLimitExceeded); "
                success_count += 1
                yt_capped += 1
                print(f"        ⏸ YouTube daily cap reached earlier — deferred (IG Reel already live)")
            else:
                print(f"        → YouTube upload...")
                try:
                    vid_id = upload_video(item, video_path, config)
                    entry["status"]  = "SUCCESS"
                    entry["video_id"] = vid_id
                    success_count += 1
                    yt_uploaded += 1
                    print(f"        ✓ https://youtube.com/shorts/{vid_id}")
                except Exception as yt_err:
                    if _is_youtube_cap(yt_err):
                        # Daily upload limit — external cap, not a failure.
                        yt_cap_hit = True
                        entry["status"] = "YT_CAPPED"
                        entry["error"] += "YouTube daily upload cap reached (uploadLimitExceeded); "
                        success_count += 1
                        yt_capped += 1
                        print(f"        ⏸ YouTube daily cap reached — deferred (IG Reel already live; verify channel to raise the limit)")
                    else:
                        raise

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
    if yt_publish:
        yt_line = f"  📺  YOUTUBE : {yt_uploaded} uploaded"
        if ig_only:
            yt_line += f", {ig_only} Instagram-only (not in top-{len(yt_signs)} rashis)"
        print(yt_line)
    if yt_capped:
        print(f"  ⏸  YT CAP  : {yt_capped}  (YouTube daily upload limit reached — verify the channel at youtube.com/verify to raise it)")
    print(f"  ❌  FAILED  : {fail_count}/{total}")
    print(f"  📄  Log     : {LOG_FILE}")
    print("=" * 60)

    # Only genuine failures fail the run. A YouTube daily-cap hit (yt_capped)
    # is an expected external limit — not a pipeline error — so it must not turn
    # the workflow red or trigger 'all jobs failed' alerts.
    if fail_count > 0:
        raise SystemExit(f"{fail_count} video(s) failed — check {LOG_FILE}")


if __name__ == "__main__":
    main()
