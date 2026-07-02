"""
test_render.py — Render ONE test video (Aries) locally.
NO upload, NO comment posting.  Just generate → TTS → video → open file.

Usage:
    python test_render.py
"""

import json
import os
import pathlib

from generate_script import generate_scripts
from tts_audio        import synthesize
from build_video      import build_video

OUT_DIR = "output"
SIGN    = "Aries"


def main():
    print("=" * 50)
    print("  TEST RENDER — Aries only, no upload")
    print("=" * 50)

    config = json.loads(pathlib.Path("config.json").read_text(encoding="utf-8"))

    # Only generate for Aries
    config_aries = dict(config)
    config_aries["signs"] = [SIGN]

    print("\n[1/3] Generating script...")
    items = generate_scripts(config_aries)
    item  = items[0]

    print(f"\n  Sign        : {item['sign']}")
    print(f"  Rasi        : {item.get('rasi_telugu', '')}")
    print(f"  Highlight   : {item.get('highlight_telugu', '')}")
    print(f"  YT Title    : {item.get('title_yt', '')}  ({len(item.get('title_yt',''))} chars)")
    print(f"\n  Audio script preview (first 200 chars):")
    print(f"  {item['script'][:200]}...")

    pathlib.Path(OUT_DIR).mkdir(exist_ok=True)

    print("\n[2/3] Synthesising audio (gTTS)...")
    audio_path = synthesize(item, OUT_DIR)
    print(f"  Audio: {audio_path}")

    print("\n[3/3] Rendering video (MoviePy)...")
    video_path = build_video(item, audio_path, config, OUT_DIR)
    print(f"\n  Video: {video_path}")

    print("\n" + "=" * 50)
    print("  DONE — opening output folder")
    print("=" * 50)

    # Open the output folder so the file is easy to find and play
    os.startfile(str(pathlib.Path(OUT_DIR).resolve()))


if __name__ == "__main__":
    main()
