import os
import pathlib
from gtts import gTTS


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

    import subprocess
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", mp3_path, "-ar", "22050", "-ac", "1", wav_path],
        capture_output=True
    )
    if result.returncode != 0:
        return mp3_path
    try:
        os.remove(mp3_path)
    except:
        pass
    return wav_path
