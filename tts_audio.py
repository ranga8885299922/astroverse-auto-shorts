import os
import re
import pathlib
import subprocess
from gtts import gTTS

# Keep every short comfortably inside the short-video window (<90s). If gTTS runs
# long we speed the voice-over up slightly (pitch-preserving) to this length —
# the video's duration follows the audio, so this caps the video too.
MAX_AUDIO_SECS = 86.0


def _bundled_ffmpeg() -> str | None:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _duration(ff: str, path: str) -> float | None:
    p = subprocess.run([ff, "-i", path], capture_output=True, text=True, errors="ignore")
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", p.stderr or "")
    if not m:
        return None
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def _cap_to_short(path: str) -> str:
    """If the voice-over exceeds MAX_AUDIO_SECS, re-time it (atempo, pitch kept)
    down to that length so the short stays under 90s. No-op when it already fits
    or ffmpeg is unavailable. Returns the path to use (may be a new file)."""
    ff = _bundled_ffmpeg()
    if not ff:
        return path
    dur = _duration(ff, path)
    if dur is None or dur <= MAX_AUDIO_SECS:
        return path
    tempo = min(dur / MAX_AUDIO_SECS, 1.6)   # cap the speed-up; guards extreme cases
    root, ext = os.path.splitext(path)
    capped = f"{root}_short{ext}"
    try:
        subprocess.run([ff, "-y", "-i", path, "-filter:a", f"atempo={tempo:.4f}",
                        "-ar", "22050", "-ac", "1", capped],
                       check=True, capture_output=True)
    except Exception:
        return path
    try:
        os.remove(path)
    except OSError:
        pass
    print(f"        voice-over {dur:.0f}s -> {MAX_AUDIO_SECS:.0f}s (short-video cap)")
    return capped


def synthesize(item: dict, out_dir: str) -> str:
    lang_code = item["language_code"]
    gtts_lang_map = {
        "te-IN": "te", "hi-IN": "hi", "ta-IN": "ta",
        "kn-IN": "kn", "bn-IN": "bn", "mr-IN": "mr",
        "ml-IN": "ml", "gu-IN": "gu",
    }
    gtts_lang = gtts_lang_map.get(lang_code, "te")
    script = item["script"]
    slug = f'{item["sign"]}_{item["language"]}'.replace(" ", "_").lower()
    mp3_path = str(pathlib.Path(out_dir) / f"{slug}.mp3")
    wav_path = str(pathlib.Path(out_dir) / f"{slug}.wav")

    print(f"        gTTS generating audio...")
    tts = gTTS(text=script, lang=gtts_lang, slow=False)
    tts.save(mp3_path)

    try:
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", mp3_path, "-ar", "22050", "-ac", "1", wav_path],
            capture_output=True
        )
        if result.returncode != 0:
            return _cap_to_short(mp3_path)
    except FileNotFoundError:
        # ffmpeg not on PATH (e.g. local Windows dev) — use mp3 directly
        return _cap_to_short(mp3_path)
    try:
        os.remove(mp3_path)
    except OSError:
        pass
    return _cap_to_short(wav_path)
