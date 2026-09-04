"""
record_scene.py — render the daily deity + rasi-emblem scene as the uploaded
video, in place of the MoviePy caption render (build_video.py). Used when
config.json has "use_scene_video": true; main.py falls back to build_video on
any error here, so a run can never fail because of the scene recorder.

Same output contract as build_video():
    build_scene_video(item, audio_path, config, out_dir) -> str
returns  output/{sign}_{language}.mp4  (H.264 / AAC, 1080x1920) with the gTTS
voice-over muxed on. optimize_for_instagram() and upload_video() consume it
unchanged, and upload keeps its title_yt ("<rasi> (date)").

How it works:
  scene/daily-scene.html is a self-contained page driven by ?sign=&day=.
  Playwright (headless Chromium) opens it at 1080x1920 and records it silently
  for the length of the voice-over; ffmpeg then muxes the audio on top.

Day selection: the deity + background theme are keyed to IST-*tomorrow*'s
weekday — the same day the rest of the pipeline targets (title date, transit
grounding and on-screen date in build_video all use IST tomorrow). The rasi
emblem is keyed to the sign.
"""

import os
import re
import glob
import pathlib
import datetime
import functools
import threading
import subprocess
from urllib.parse import quote
from zoneinfo import ZoneInfo
from http.server import HTTPServer, SimpleHTTPRequestHandler

SCENE_DIR = str(pathlib.Path(__file__).parent / "scene")

# item["sign"] is capitalised English ("Aries"); the scene wants the slug.
SIGN_SLUG = {
    "Aries": "aries", "Taurus": "taurus", "Gemini": "gemini", "Cancer": "cancer",
    "Leo": "leo", "Virgo": "virgo", "Libra": "libra", "Scorpio": "scorpio",
    "Sagittarius": "sagittarius", "Capricorn": "capricorn",
    "Aquarius": "aquarius", "Pisces": "pisces",
}


def _scene_title(item) -> str:
    """On-screen title — the exact YouTube/IG title ("<rasi telugu> (Sep 05
    2026)"), so what viewers read matches the upload title. Rebuilds it from
    rasi_telugu + IST-tomorrow's date if title_yt is somehow absent."""
    t = item.get("title_yt")
    if t:
        return t
    rasi = item.get("rasi_telugu") or item.get("sign", "")
    try:
        from generate_script import _ist_tomorrow
        date_short = _ist_tomorrow().strftime("%b %d %Y")
    except Exception:
        date_short = (datetime.datetime.now(ZoneInfo("Asia/Kolkata"))
                      + datetime.timedelta(days=1)).strftime("%b %d %Y")
    return f"{rasi} ({date_short})"


def _scene_day() -> str:
    """English weekday name the scene themes to — IST tomorrow, matching the
    date/transit the rest of the pipeline uses. Reuses generate_script's frozen
    tomorrow so it can't drift across an IST midnight mid-run; falls back to a
    direct compute if that import is unavailable."""
    try:
        from generate_script import _ist_tomorrow
        return _ist_tomorrow().strftime("%A")
    except Exception:
        return (datetime.datetime.now(ZoneInfo("Asia/Kolkata"))
                + datetime.timedelta(days=1)).strftime("%A")


def _audio_duration(audio_path: str) -> float:
    """Seconds of the gTTS clip (mp3 locally, wav in CI), read from ffmpeg's
    banner so the recorder needs only playwright + imageio-ffmpeg (no moviepy)."""
    proc = subprocess.run([_ffmpeg_exe(), "-i", audio_path],
                          capture_output=True, text=True, errors="ignore")
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", proc.stderr or "")
    if not m:
        raise RuntimeError(f"could not read audio duration from {audio_path}")
    h, mn, s = m.groups()
    return int(h) * 3600 + int(mn) * 60 + float(s)


def _ffmpeg_exe() -> str:
    """Bundled ffmpeg (has libx264) so muxing works on local Windows where
    system ffmpeg isn't on PATH; in CI apt installs ffmpeg anyway."""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def _serve(dir_path: str):
    """Serve the scene folder on an ephemeral localhost port (file:// with
    relative image src is unreliable in headless Chromium)."""
    handler = functools.partial(SimpleHTTPRequestHandler, directory=dir_path)
    httpd = HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def build_scene_video(item, audio_path, config, out_dir) -> str:
    from playwright.sync_api import sync_playwright

    vc = config.get("video", {})
    W, H = int(vc.get("width", 1080)), int(vc.get("height", 1920))

    sign = SIGN_SLUG.get(item["sign"], str(item["sign"]).strip().lower())
    day = _scene_day()
    title = _scene_title(item)
    dur = _audio_duration(audio_path)
    # Record longer than the voice-over so the muxed clip never ends short; the
    # ffmpeg -shortest below trims the tail back to the audio length.
    rec_ms = int(dur * 1000) + 1500

    slug = f'{item["sign"]}_{item["language"]}'.replace(" ", "_").lower()
    rec_dir = pathlib.Path(out_dir) / "_scene_rec"
    rec_dir.mkdir(parents=True, exist_ok=True)
    for old in glob.glob(str(rec_dir / "*.webm")):
        try:
            os.remove(old)
        except OSError:
            pass

    httpd, port = _serve(SCENE_DIR)
    try:
        url = (f"http://127.0.0.1:{port}/daily-scene.html"
               f"?sign={sign}&day={day}&title={quote(title)}")
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--force-color-profile=srgb"])
            ctx = browser.new_context(
                viewport={"width": W, "height": H},
                device_scale_factor=1,
                record_video_dir=str(rec_dir),
                record_video_size={"width": W, "height": H},
            )
            page = ctx.new_page()
            page.goto(url, wait_until="networkidle")
            try:
                page.wait_for_function("window.__sceneReady === true", timeout=8000)
            except Exception:
                pass  # hard cap in the page sets it after 4s regardless
            page.wait_for_timeout(rec_ms)
            ctx.close()        # finalises the .webm
            browser.close()
        webms = sorted(glob.glob(str(rec_dir / "*.webm")), key=os.path.getmtime)
        if not webms:
            raise RuntimeError("Playwright produced no recording")
        webm = webms[-1]
    finally:
        httpd.shutdown()

    out = str(pathlib.Path(out_dir) / f"{slug}.mp4")
    ff = _ffmpeg_exe()
    # Video from the silent recording, audio from gTTS. -shortest ends the clip
    # when the audio ends (the recording is deliberately ~1.5s longer).
    cmd = [
        ff, "-y",
        "-i", webm,
        "-i", audio_path,
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-r", "30",
        "-c:a", "aac", "-b:a", "160k",
        "-movflags", "+faststart", "-shortest",
        out,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    try:
        os.remove(webm)
    except OSError:
        pass
    return out
