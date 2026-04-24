import textwrap
import pathlib
import os
import datetime
import urllib.request
from zoneinfo import ZoneInfo

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

# ── Font paths ────────────────────────────────────────────────────────────────
TELUGU_FONT_URL = "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansTelugu/NotoSansTelugu-Regular.ttf"
TELUGU_FONT_PATH = "fonts/NotoSansTelugu-Regular.ttf"

def ensure_telugu_font():
    """Download Telugu font if not present."""
    if not os.path.exists("fonts"):
        os.makedirs("fonts")
    if not os.path.exists(TELUGU_FONT_PATH):
        print("  Downloading Telugu font...")
        try:
            urllib.request.urlretrieve(TELUGU_FONT_URL, TELUGU_FONT_PATH)
            print("  ✓ Telugu font downloaded")
        except Exception as e:
            print(f"  ⚠ Telugu font download failed: {e}")
            return None
    return TELUGU_FONT_PATH


def find_font(preferred_names):
    search_dirs = [
        r"C:\Windows\Fonts",
        os.path.expanduser(r"~\AppData\Local\Microsoft\Windows\Fonts"),
        "/usr/share/fonts/truetype/msttcorefonts",
        "/usr/share/fonts/truetype/dejavu",
        "/usr/share/fonts/truetype/noto",
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
        wrapped = "\n".join(textwrap.wrap(chunk, width=30))
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
    W        = vc["width"]
    H        = vc["height"]

    # Get IST date
    ist_now  = datetime.datetime.now(ZoneInfo("Asia/Kolkata"))
    date_str = ist_now.strftime("%b %d %Y")

    symbol      = SIGN_SYMBOLS.get(item["sign"], "🔮")
    rasi_telugu = item.get("rasi_telugu", item["sign"])

    # Ensure Telugu font available
    telugu_font = ensure_telugu_font()
    if not telugu_font:
        telugu_font = FONT_REGULAR  # fallback

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
    # TOP SECTION — Date (big, bright, first thing seen)
    # ════════════════════════════════════════════════════════
    top_bar = (ColorClip(size=(W, int(H * 0.20)), color=(0, 0, 0))
               .with_opacity(0.65).with_duration(dur).with_position((0, 0)))
    layers.append(top_bar)

    # DATE — very large white
    layers.append(make_text(
        text         = date_str,
        font_path    = FONT_BOLD,
        font_size    = 78,
        color        = "#FFFFFF",
        width        = W - 20,
        position     = ("center", 0.01),
        duration     = dur,
        stroke_color = "#000000",
        stroke_width = 4,
    ))

    # Telugu Rasi name in Telugu font under date
    layers.append(make_text(
        text         = f"{symbol} {rasi_telugu} {symbol}",
        font_path    = telugu_font,
        font_size    = 52,
        color        = "#FFD700",
        width        = W - 40,
        position     = ("center", 0.10),
        duration     = dur,
        stroke_color = "#000000",
        stroke_width = 3,
    ))

    # ════════════════════════════════════════════════════════
    # MIDDLE SECTION — Scrolling script (6 parts)
    # ════════════════════════════════════════════════════════
    display_script = item.get("script_display", item.get("script", ""))
    parts    = split_script_into_parts(display_script, NUM_PARTS)
    part_dur = dur / NUM_PARTS

    for idx, part_text in enumerate(parts):
        start_t = idx * part_dur

        layers.append(make_text(
            text      = f"({idx+1}/{NUM_PARTS})",
            font_path = FONT_REGULAR,
            font_size = 24,
            color     = "#FFD700",
            width     = W - 60,
            position  = ("center", 0.21),
            duration  = part_dur,
            start     = start_t,
            stroke_width = 1,
        ))

        layers.append(make_text(
            text      = part_text,
            font_path = FONT_CAPTION,
            font_size = 40,
            color     = "#FFFFFF",
            width     = W - 60,
            position  = ("center", 0.26),
            duration  = part_dur,
            start     = start_t,
            stroke_width = 2,
        ))

    # ════════════════════════════════════════════════════════
    # BOTTOM SECTION — Big sign name + promo
    # ════════════════════════════════════════════════════════
    bottom_bar = (ColorClip(size=(W, int(H * 0.25)), color=(0, 0, 0))
                  .with_opacity(0.65).with_duration(dur)
                  .with_position((0, int(H * 0.75))))
    layers.append(bottom_bar)

    # Telugu rasi name BIG at bottom — most visible in YouTube scroll
    layers.append(make_text(
        text         = f"{symbol} {rasi_telugu} {symbol}",
        font_path    = telugu_font,
        font_size    = 88,
        color        = "#FFD700",
        width        = W - 20,
        position     = ("center", 0.76),
        duration     = dur,
        stroke_color = "#000000",
        stroke_width = 5,
    ))

    # Promo
    layers.append(make_text(
        text      = "⬇ Download Astroverse App\nLink in channel description",
        font_path = FONT_CAPTION,
        font_size = 30,
        color     = "#FFFFFF",
        width     = W - 80,
        position  = ("center", 0.89),
        duration  = dur,
        stroke_width = 2,
    ))

    # ── Compose & export ──────────────────────────────────────────────────────
    final = CompositeVideoClip(layers).with_audio(audio)

    slug = f'{item["sign"]}_{item["language"]}'.replace(" ", "_").lower()
    out  = str(pathlib.Path(out_dir) / f"{slug}.mp4")

    final.write_videofile(
        out, fps=30, codec="libx264",
        audio_codec="aac", threads=4,
        preset="fast", logger=None,
    )
    return out
