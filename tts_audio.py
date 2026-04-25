import os
import pathlib
import io
import wave

# gTTS - completely free, no API key needed
from gtts import gTTS


def synthesize(item: dict, out_dir: str) -> str:
    """
    Uses gTTS (Google Translate TTS) - free, no limits.
    Converts Telugu script to speech and saves as .wav file.
    """
    lang_code = item["language_code"]

    # gTTS language code mapping
    gtts_lang_map = {
        "te-IN": "te",
        "hi-IN": "hi",
        "ta-IN": "ta",
        "kn-IN": "kn",
        "bn-IN": "bn",
        "mr-IN": "mr",
        "ml-IN": "ml",
        "gu-IN": "gu",
    }
    gtts_lang = gtts_lang_map.get(lang_code, "te")

    script = item["script"]

    # gTTS saves as MP3 — we save directly as mp3 then convert
    slug = f'{item["sign"]}_{item["language"]}'.replace(" ", "_").lower()
    mp3_path = str(pathlib.Path(out_dir) / f"{slug}.mp3")
    wav_path = str(pathlib.Path(out_dir) / f"{slug}.wav")

    print(f"        gTTS generating audio...")
    tts = gTTS(text=script, lang=gtts_lang, slow=False)
    tts.save(mp3_path)

    # Convert mp3 to wav using ffmpeg (already installed in GitHub Actions)
    import subprocess
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", mp3_path, "-ar", "22050", "-ac", "1", wav_path],
        capture_output=True
    )
    if result.returncode != 0:
        # If ffmpeg fails, just return mp3 path — moviepy can handle mp3 too
        return mp3_path

    # Clean up mp3
    try:
        os.remove(mp3_path)
    except:
        pass

    return wav_path
