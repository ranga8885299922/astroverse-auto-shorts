import textwrap
import pathlib
import os
import datetime
import numpy as np

try:
    from moviepy import (
        VideoFileClip, ImageClip, AudioFileClip,
        TextClip, CompositeVideoClip, concatenate_videoclips,
        ColorClip,
    )
except ImportError:
    from moviepy.editor import (
        VideoFileClip, ImageClip, AudioFileClip,
        TextClip, CompositeVideoClip, concatenate_videoclips,
        ColorClip,
    )


def find_font(preferred_names):
    search_dirs = [
        r"C:\Windows\Fonts",
        os.path.expanduser(r"~\AppData\Local\Microsoft\Windows\Fonts"),
        "/usr/share/fonts/truetype/msttcorefonts",
        "/usr/share/fonts/truetype/dejavu",
        "/usr/share/fonts/truetype",
        "/usr/share/fonts",
        "/usr/local/share/fonts",
    ]
    for name in preferred_names:
        for d in search_dirs:
            for candidate in [os.path.join(d, name), os.path.join(d, name.lower())]:
                if os.path.isfile(candidate):
                    return candidate
    return None


FONT_REGULAR = find_font(["arial.ttf", "Arial.ttf", "DejaVuSans.ttf", "FreeSans.ttf"])
FONT_BOLD    = find_font(["arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf", "FreeSansBold.ttf"])
FONT_SIGN    = FONT_BOLD    or FONT_REGULAR
FONT_CAPTION = FONT_REGULAR or FONT_SIGN
FONT_PROMO   = FONT_REGULAR or FONT_SIGN

NUM_PARTS = 6

SIGN_SYMBOLS = {
    "Aries": "♈", "Taurus": "♉", "Gemini": "♊", "Cancer": "♋",
    "Leo": "♌", "Virgo": "♍", "Libra": "♎", "Scorpio": "♏",
    "Sagittarius": "♐", "Capricorn": "♑", "Aquarius": "♒", "Pisces": "♓"
}


def split_script_into_parts(script: str, num_parts: int = NUM_PARTS) -> list[str]:
    words = script.split()
    total = len(words)
    size  = max(1, total // num_parts)
    parts = []
    for i in range(num_parts):
        start   = i * size
        end     = start + size if i < num_parts - 1 else total
        chunk   = " ".join(words[start:end])
        wrapped = "\n".join(textwrap.wrap(chunk, width=28))
        parts.append(wrapped)
    return parts


def make_text(text, font_path, font_size, color, width, position, duration,
              stroke_color="black", stroke_width=2, method="caption", start=0):
    kwargs = dict(
        text         = text,
        font_size    = font_size,
        color        = color,
        stroke_color = stroke_color,
        stroke_width = stroke_width,
    )
    if font_path:
        kwargs["font"] = font_path
    if method == "caption":
        kwargs["method"]     = "caption"
        kwargs["size"]       = (width, None)
        kwargs["text_align"] = "center"

    clip = TextClip(**kwargs).with_duration(duration)
    if start > 0:
        clip = clip.with_start(start)
    return clip.with_position(position, relative=True)


def build_video(item: dict, audio_path: str, config: dict, out_dir: str) -> str:
    vc       = config["video"]
    W        = vc["width"]    # 1080
    H        = vc["height"]   # 1920
    date_str = datetime.date.today().strftime("%b %d %Y")
    symbol   = SIGN_SYMBOLS.get(item["sign"], "🔮")

    # ── Audio ─────────────────────────────────────────────────────────────────
    audio = AudioFileClip(audio_path)
    dur   = audio.duration

    # ── Background ────────────────────────────────────────────────────────────
    bg_path = vc["background_file"]
    if bg_path.lower().endswith((".mp4", ".mov", ".avi")):
        bg = VideoFileClip(bg_path).without_audio()
        if bg.duration < dur:
            loops = int(dur / bg.duration) + 2
            bg = concatenate_videoclips([bg] * loops)
        bg = bg.subclipped(0, dur).resized((W, H))
    else:
        bg = ImageClip(bg_path).with_duration(dur).resized((W, H))

    layers = [bg]

    # ════════════════════════════════════════════════════════
    # TOP SECTION — Date (very prominent, first thing seen)
    # ════════════════════════════════════════════════════════

    # Dark overlay — top 22% of screen
    layers.append(
        ColorClip(size=(W, int(H * 0.22)), color=(0, 0, 0))
        .with_opacity(0.65)
        .with_duration(dur)
        .with_position((0, 0))
    )

    # DATE — top, very large and bright
    layers.append(make_text(
        text         = date_str,
        font_path    = FONT_BOLD,
        font_size    = 72,
        color        = "#FFFFFF",
        width        = W - 20,
        position     = ("center", 0.01),
        duration     = dur,
        stroke_color = "#000000",
        stroke_width = 4,
    ))

    # Language label under date
    layers.append(make_text(
        text      = "🔮 Telugu Daily Horoscope 🔮",
        font_path = FONT_REGULAR,
        font_size = 34,
        color     = "#FFD700",
        width     = W - 40,
        position  = ("center", 0.09),
        duration  = dur,
        stroke_width = 2,
    ))

    # ════════════════════════════════════════════════════════
    # MIDDLE SECTION — Scrolling script text
    # ════════════════════════════════════════════════════════

    display_script = item.get("script_display", item["script"])
    parts    = split_script_into_parts(display_script, NUM_PARTS)
    part_dur = dur / NUM_PARTS

    for idx, part_text in enumerate(parts):
        start_t = idx * part_dur

        # Part indicator
        layers.append(make_text(
            text      = f"({idx+1}/{NUM_PARTS})",
            font_path = FONT_REGULAR,
            font_size = 26,
            color     = "#FFD700",
            width     = W - 60,
            position  = ("center", 0.22),
            duration  = part_dur,
            start     = start_t,
            stroke_width = 1,
        ))

        # Script text
        layers.append(make_text(
            text      = part_text,
            font_path = FONT_CAPTION,
            font_size = 42,
            color     = "#FFFFFF",
            width     = W - 60,
            position  = ("center", 0.27),
            duration  = part_dur,
            start     = start_t,
            stroke_width = 2,
        ))

    # ════════════════════════════════════════════════════════
    # BOTTOM SECTION — Sign name BIG + Promo
    # ════════════════════════════════════════════════════════

    # Dark overlay — bottom 28% of screen
    layers.append(
        ColorClip(size=(W, int(H * 0.28)), color=(0, 0, 0))
        .with_opacity(0.65)
        .with_duration(dur)
        .with_position((0, int(H * 0.72)))
    )

    # SIGN NAME — large, at bottom, highly visible in thumbnails
    layers.append(make_text(
        text         = f"{symbol}  {item['sign'].upper()}  {symbol}",
        font_path    = FONT_SIGN,
        font_size    = 110,
        color        = "#FFD700",
        width        = W - 20,
        position     = ("center", 0.73),
        duration     = dur,
        stroke_color = "#000000",
        stroke_width = 5,
    ))

    # Promo text
    layers.append(make_text(
        text      = "⬇ Download Astroverse App\nLink in channel description",
        font_path = FONT_PROMO,
        font_size = 32,
        color     = "#FFFFFF",
        width     = W - 80,
        position  = ("center", 0.88),
        duration  = dur,
        stroke_width = 2,
    ))

    # ── Compose & export ──────────────────────────────────────────────────────
    final = CompositeVideoClip(layers).with_audio(audio)

    slug = f'{item["sign"]}_{item["language"]}'.replace(" ", "_").lower()
    out  = str(pathlib.Path(out_dir) / f"{slug}.mp4")

    final.write_videofile(
        out,
        fps         = 30,
        codec       = "libx264",
        audio_codec = "aac",
        threads     = 4,
        preset      = "fast",
        logger      = None,
    )
    return out
