import textwrap
import pathlib
import os
import datetime
import urllib.request
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw
import numpy as np

try:
    from moviepy import (
        ImageClip, AudioFileClip, TextClip,
        CompositeVideoClip, ColorClip,
    )
except ImportError:
    from moviepy.editor import (
        ImageClip, AudioFileClip, TextClip,
        CompositeVideoClip, ColorClip,
    )

# ── Conversion CTA overlay constants (edit here) ─────────────────────────────
# ONE overlay only — at the hook (CTA_START → CTA_END). No end-card.
# 3 stacked clips: Telugu | Latin (gold) | Telugu
# NotoSansTelugu has no Latin glyphs, so Latin words use FONT_BOLD/Arial.
# Telugu words use NotoSansTelugu-Bold. Never mix both in one TextClip.
CTA_SCREEN_TEL1    = "మీ personal జాతకం"               # Telugu words  (NotoSansTelugu-Bold)
CTA_SCREEN_LATIN   = "astroloz.com - completely free"   # Latin words   (FONT_BOLD/Arial, gold)
CTA_SCREEN_TEL2    = "లింక్ కింద కామెంట్‌లో ఉంది"      # Telugu line 2 (NotoSansTelugu-Bold)
CTA_START          = 10          # seconds — overlay appears
CTA_END            = 16          # seconds — overlay disappears
CTA_BOX_Y          = 1380        # absolute Y pixel — top of background box
CTA_BOX_H          = 235         # height for 3-line layout
CTA_TEL1_Y_REL     = 0.724       # top of Telugu line 1  (≈ y 1390)
CTA_LATIN_Y_REL    = 0.750       # top of Latin line     (≈ y 1440)
CTA_TEL2_Y_REL     = 0.787       # top of Telugu line 2  (≈ y 1511)
# ─────────────────────────────────────────────────────────────────────────────

TELUGU_FONT_URL      = "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansTelugu/NotoSansTelugu-Regular.ttf"
TELUGU_FONT_BOLD_URL = "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansTelugu/NotoSansTelugu-Bold.ttf"
TELUGU_FONT_PATH     = "fonts/NotoSansTelugu-Regular.ttf"
TELUGU_BOLD_PATH     = "fonts/NotoSansTelugu-Bold.ttf"

def ensure_fonts():
    import time
    os.makedirs("fonts", exist_ok=True)
    for url, path in [(TELUGU_FONT_URL, TELUGU_FONT_PATH),
                      (TELUGU_FONT_BOLD_URL, TELUGU_BOLD_PATH)]:
        if os.path.exists(path) and os.path.getsize(path) > 10_000:
            continue
        for attempt in range(3):
            try:
                print(f"  Downloading font: {path} (attempt {attempt+1})")
                urllib.request.urlretrieve(url, path)
                if os.path.getsize(path) > 10_000:
                    break
                os.remove(path)
            except Exception as e:
                print(f"  Font download failed: {e}")
                if attempt < 2:
                    time.sleep(5)

def find_font(names):
    dirs = [r"C:\Windows\Fonts","/usr/share/fonts/truetype/msttcorefonts",
            "/usr/share/fonts/truetype/dejavu","/usr/share/fonts/truetype",
            "/usr/share/fonts"]
    for n in names:
        for d in dirs:
            p = os.path.join(d, n)
            if os.path.isfile(p):
                return p
    return None

FONT_REGULAR = find_font(["arial.ttf","Arial.ttf","DejaVuSans.ttf","FreeSans.ttf"])
FONT_BOLD    = find_font(["arialbd.ttf","Arial Bold.ttf","DejaVuSans-Bold.ttf","FreeSansBold.ttf"])

NUM_PARTS      = 6
HIGHLIGHT_SECS = 5

SIGN_SYMBOLS = {
    "Aries":"♈","Taurus":"♉","Gemini":"♊","Cancer":"♋",
    "Leo":"♌","Virgo":"♍","Libra":"♎","Scorpio":"♏",
    "Sagittarius":"♐","Capricorn":"♑","Aquarius":"♒","Pisces":"♓"
}

def make_orange_bg(W, H):
    img  = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)
    for y in range(H):
        r = y / H
        R = int(220 + (160-220)*r)
        G = int(80  + (120-80) *r)
        B = int(20  + (0  -20) *r)
        draw.line([(0,y),(W,y)], fill=(R,G,B))
    return np.array(img)

def split_script(script, num_parts=NUM_PARTS):
    words = script.split()
    total = len(words)
    size  = max(1, total // num_parts)
    parts = []
    for i in range(num_parts):
        s = i * size
        e = s + size if i < num_parts - 1 else total
        parts.append("\n".join(textwrap.wrap(" ".join(words[s:e]), width=20)))
    return parts

def _make_cta_overlay(tel1, latin_line, tel2, start, duration, W, tel_bold, font_bold):
    """
    Returns 4 layers: dark bg box | Telugu line 1 | Latin line (gold) | Telugu line 2.
    Latin and Telugu are in separate TextClips — NotoSansTelugu has no Latin glyphs.
    tel1/tel2 use tel_bold (NotoSansTelugu-Bold); latin_line uses font_bold (Arial).
    """
    return [
        ColorClip(size=(W, CTA_BOX_H), color=(0, 0, 0))
            .with_opacity(0.72)
            .with_start(start).with_duration(duration)
            .with_position((0, CTA_BOX_Y)),
        make_text(tel1, tel_bold, 44, "#FFFFFF", W - 40,
                  ("center", CTA_TEL1_Y_REL), duration,
                  stroke_width=2, start=start),
        make_text(latin_line, font_bold, 46, "#FFD700", W - 40,
                  ("center", CTA_LATIN_Y_REL), duration,
                  stroke_color="#000000", stroke_width=3, start=start),
        make_text(tel2, tel_bold, 40, "#FFFFFF", W - 40,
                  ("center", CTA_TEL2_Y_REL), duration,
                  stroke_width=2, start=start),
    ]


def make_text(text, font_path, font_size, color, width, position, duration,
              stroke_color="black", stroke_width=2, method="caption", start=0):
    kw = dict(text=text, font_size=font_size, color=color,
              stroke_color=stroke_color, stroke_width=stroke_width)
    if font_path:
        kw["font"] = font_path
    if method == "caption":
        kw["method"]     = "caption"
        kw["size"]       = (width, None)
        kw["text_align"] = "center"
    clip = TextClip(**kw).with_duration(duration)
    if start > 0:
        clip = clip.with_start(start)
    return clip.with_position(position, relative=True)

def build_video(item, audio_path, config, out_dir):
    ensure_fonts()
    vc   = config["video"]
    W, H = vc["width"], vc["height"]

    ist_now  = datetime.datetime.now(ZoneInfo("Asia/Kolkata"))
    tomorrow = ist_now + datetime.timedelta(days=1)
    date_str = tomorrow.strftime("%b %d %Y")

    symbol         = SIGN_SYMBOLS.get(item["sign"], "🔮")
    rasi           = item.get("rasi_telugu", item["sign"])
    highlight_text = item.get("highlight_telugu", rasi)

    tel_bold = TELUGU_BOLD_PATH if os.path.exists(TELUGU_BOLD_PATH) else \
               TELUGU_FONT_PATH if os.path.exists(TELUGU_FONT_PATH) else FONT_BOLD
    tel_reg  = TELUGU_FONT_PATH if os.path.exists(TELUGU_FONT_PATH) else FONT_REGULAR

    audio = AudioFileClip(audio_path)
    dur   = audio.duration
    bg    = ImageClip(make_orange_bg(W, H)).with_duration(dur)
    layers = [bg]

    # ═══════════════════════════════════════════
    # FIRST 5 SECONDS — HIGHLIGHT (thumbnail)
    # ═══════════════════════════════════════════
    layers.append(
        ColorClip(size=(W,H), color=(0,0,0))
        .with_opacity(0.35).with_duration(HIGHLIGHT_SECS).with_position((0,0))
    )
    layers.append(make_text(symbol, FONT_BOLD, 130, "#FFD700", W-20,
                            ("center",0.02), HIGHLIGHT_SECS, stroke_width=4))
    layers.append(make_text(rasi, tel_bold, 90, "#FFFFFF", W-20,
                            ("center",0.12), HIGHLIGHT_SECS, stroke_width=5))
    layers.append(make_text(highlight_text, tel_bold, 72, "#FFD700", W-40,
                            ("center",0.38), HIGHLIGHT_SECS,
                            stroke_color="#000000", stroke_width=4))
    layers.append(make_text(f"📅 {date_str}", FONT_BOLD, 44, "#FFFFFF", W-40,
                            ("center",0.86), HIGHLIGHT_SECS, stroke_width=3))

    # ═══════════════════════════════════════════
    # AFTER 5 SECONDS — Main video
    # ═══════════════════════════════════════════
    main_dur   = dur - HIGHLIGHT_SECS
    main_start = HIGHLIGHT_SECS

    # Top bar
    layers.append(
        ColorClip(size=(W, int(H*0.28)), color=(0,0,0))
        .with_opacity(0.45).with_duration(main_dur)
        .with_start(main_start).with_position((0,0))
    )
    layers.append(make_text(symbol, FONT_BOLD, 100, "#FFD700", W-20,
                            ("center",0.01), main_dur, stroke_width=4, start=main_start))
    layers.append(make_text(rasi, tel_bold, 83, "#FFFFFF", W-20,
                            ("center",0.09), main_dur, stroke_width=5, start=main_start))
    # Date bar
    layers.append(
        ColorClip(size=(W,75), color=(160,50,0))
        .with_duration(main_dur).with_start(main_start)
        .with_position((0, int(H*0.28)))
    )
    layers.append(make_text(f"📅 {date_str} | Telugu Horoscope",
                            FONT_BOLD, 34, "#FFFFFF", W-20,
                            ("center",0.285), main_dur, stroke_width=2, start=main_start))

    # Script in Telugu — 6 parts scrolling
    # Use only script_telugu (without promo) for display
    telugu_script = item.get("script_telugu", item.get("script",""))
    parts    = split_script(telugu_script, NUM_PARTS)
    part_dur = main_dur / NUM_PARTS

    for idx, part in enumerate(parts):
        st = main_start + idx * part_dur
        layers.append(make_text(f"({idx+1}/{NUM_PARTS})", tel_reg, 26,
                                "#FFD700", W-60, ("center",0.345),
                                part_dur, stroke_width=1, start=st))
        layers.append(make_text(part, tel_bold, 83, "#FFFFFF", W-40,
                                ("center",0.375), part_dur,
                                stroke_width=3, start=st))

    # ═══════════════════════════════════════════
    # HOOK CTA OVERLAY  (CTA_START → CTA_END seconds)
    # 3-layer: Telugu | Latin (gold) | Telugu
    # Only one CTA — no end-card.
    # ═══════════════════════════════════════════
    if dur > CTA_END:
        cta_dur = CTA_END - CTA_START
        layers.extend(_make_cta_overlay(
            CTA_SCREEN_TEL1, CTA_SCREEN_LATIN, CTA_SCREEN_TEL2,
            CTA_START, cta_dur, W, tel_bold, FONT_BOLD,
        ))

    final = CompositeVideoClip(layers).with_audio(audio)
    slug  = f'{item["sign"]}_{item["language"]}'.replace(" ","_").lower()
    out   = str(pathlib.Path(out_dir) / f"{slug}.mp4")
    final.write_videofile(out, fps=30, codec="libx264",
                          audio_codec="aac", threads=4,
                          preset="fast", logger=None)
    return out
