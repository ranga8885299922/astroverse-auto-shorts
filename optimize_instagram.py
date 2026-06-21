"""
optimize_instagram.py — Prepare a rendered Short for Instagram Reels.

The pipeline already renders 1080x1920 H.264 + AAC @ 30fps, which IS the
Instagram Reels spec. The only meaningful optimisation is moving the moov
atom to the front (`+faststart`) so the file streams/uploads cleanly — this
is a fast, lossless stream-copy, no re-encode.

If ffmpeg is not available (e.g. local Windows dev), we fall back to a plain
file copy so the pipeline never breaks.
"""

import os
import shutil
import pathlib
import subprocess

# Instagram Reels reference spec (source already matches these):
#   resolution 1080x1920 (9:16) | H.264 video | AAC audio | 30 fps | <=90 s
FASTSTART_ARGS = ["-c", "copy", "-movflags", "+faststart"]


def optimize_for_instagram(video_path: str, out_dir: str) -> str:
    """
    Returns the path to the Instagram-ready file inside out_dir.
    Uses ffmpeg +faststart (lossless) when available, else copies the file.
    """
    pathlib.Path(out_dir).mkdir(parents=True, exist_ok=True)
    src  = pathlib.Path(video_path)
    dest = str(pathlib.Path(out_dir) / f"{src.stem}_insta.mp4")

    try:
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", str(src), *FASTSTART_ARGS, dest],
            capture_output=True,
        )
        if result.returncode == 0 and os.path.exists(dest) \
                and os.path.getsize(dest) > 0:
            return dest
        # ffmpeg ran but produced nothing usable → fall back to copy
    except FileNotFoundError:
        pass  # ffmpeg not installed (local Windows) → fall back to copy

    shutil.copyfile(src, dest)
    return dest
