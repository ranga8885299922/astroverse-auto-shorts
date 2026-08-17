import json
import os
import time
import datetime
import urllib.request
import urllib.error
from zoneinfo import ZoneInfo
from groq import Groq

# ── Conversion CTA — spoken (gTTS audio) ─────────────────────────────────────
# Inserted at a sentence boundary so it never cuts mid-sentence.
# Engagement CTA: viewers comment "link" → auto-reply delivers the website
# link (drives comment count, which the algorithm rewards).
CTA_SPOKEN = (
    "మీ వ్యక్తిగత జాతకం గురించి ప్రశ్నలకు పూర్తి ఉచిత సమాధానాల కోసం "
    "link అని comment చేయండి."
    " నేను website link reply ఇస్తాను."
)

# ── YouTube title — "{rasi}: {hook} | {date}" (edit here) ────────────────────
# Rasi name FIRST so viewers instantly see whose prediction it is, then this
# video's own hook. rasi_telugu already contains "రాశి" so the search keyword
# is naturally present. Capped at 100 chars; the hook is truncated first.


def build_title(highlight: str, rasi: str, date_short: str) -> str:
    prefix = f"{rasi}: "
    suffix = f" | {date_short}"
    hl     = " ".join(highlight.split())          # collapse newlines/spaces
    max_hl = 100 - len(prefix) - len(suffix)
    if len(hl) > max_hl:
        hl = hl[:max_hl - 1].rstrip() + "…"
    return prefix + hl + suffix

RASI_TELUGU = {
    "Aries":"మేష రాశి","Taurus":"వృషభ రాశి","Gemini":"మిథున రాశి",
    "Cancer":"కర్కాటక రాశి","Leo":"సింహ రాశి","Virgo":"కన్యా రాశి",
    "Libra":"తుల రాశి","Scorpio":"వృశ్చిక రాశి","Sagittarius":"ధనుస్సు రాశి",
    "Capricorn":"మకర రాశి","Aquarius":"కుంభ రాశి","Pisces":"మీన రాశి",
}

# Rasi lord + element — forces astrologically DIFFERENT reasoning per sign,
# so 4 family members with 4 rasis never hear the same prediction.
RASI_LORD = {
    "Aries": "కుజుడు (Mars)",      "Taurus": "శుక్రుడు (Venus)",
    "Gemini": "బుధుడు (Mercury)",   "Cancer": "చంద్రుడు (Moon)",
    "Leo": "సూర్యుడు (Sun)",        "Virgo": "బుధుడు (Mercury)",
    "Libra": "శుక్రుడు (Venus)",    "Scorpio": "కుజుడు (Mars)",
    "Sagittarius": "గురువు (Jupiter)", "Capricorn": "శని (Saturn)",
    "Aquarius": "శని (Saturn)",     "Pisces": "గురువు (Jupiter)",
}
RASI_ELEMENT = {
    "Aries": "అగ్ని", "Leo": "అగ్ని", "Sagittarius": "అగ్ని",
    "Taurus": "భూమి", "Virgo": "భూమి", "Capricorn": "భూమి",
    "Gemini": "వాయు", "Libra": "వాయు", "Aquarius": "వాయు",
    "Cancer": "జలం", "Scorpio": "జలం", "Pisces": "జలం",
}

# Daily rotating focus — on any given day all 12 signs get DIFFERENT focus
# areas, and each sign's focus changes every day. Kills same-hook syndrome.
FOCUS_ROTATION = [
    "కెరీర్ లో పెద్ద మార్పు", "అనుకోని ధన లాభం", "ప్రేమ & వివాహ విషయాలు",
    "ఆరోగ్యంలో మలుపు", "కుటుంబ శుభవార్త", "విద్య & పోటీ పరీక్షలు",
    "వ్యాపార అవకాశం", "ప్రయాణ యోగం", "ఆస్తి & వాహన విషయాలు",
    "ఆధ్యాత్మిక పురోగతి", "పాత మిత్రుల కలయిక", "కొత్త ప్రారంభాలు",
]

SIGN_SYMBOLS = {
    "Aries":"♈","Taurus":"♉","Gemini":"♊","Cancer":"♋",
    "Leo":"♌","Virgo":"♍","Libra":"♎","Scorpio":"♏",
    "Sagittarius":"♐","Capricorn":"♑","Aquarius":"♒","Pisces":"♓"
}

# Each sign's ruling planet — used to make lucky colour / number / remedy
# astrologically CONSISTENT with the rasi (and therefore different across
# signs, killing the "every sign got blue" repetition).
SIGN_PLANET = {
    "Aries":"Mars","Taurus":"Venus","Gemini":"Mercury","Cancer":"Moon",
    "Leo":"Sun","Virgo":"Mercury","Libra":"Venus","Scorpio":"Mars",
    "Sagittarius":"Jupiter","Capricorn":"Saturn","Aquarius":"Saturn","Pisces":"Jupiter",
}
# planet → (lucky colour, lucky number, remedy) — traditional Vedic associations
LUCKY_TE = {
    "Sun":     ("ఎరుపు లేదా నారింజ", 1, "ఆదివారం సూర్యుడికి ఉదయాన్నే జలం సమర్పించండి"),
    "Moon":    ("తెలుపు లేదా వెండి రంగు", 2, "సోమవారం శివుడికి పాలతో అభిషేకం చేయండి"),
    "Mars":    ("ఎరుపు", 9, "మంగళవారం ఆంజనేయస్వామికి సింధూరం సమర్పించండి"),
    "Mercury": ("ఆకుపచ్చ", 5, "బుధవారం గణపతికి గరిక సమర్పించండి"),
    "Jupiter": ("పసుపు లేదా బంగారు రంగు", 3, "గురువారం విష్ణువుకు పసుపు పూలు సమర్పించండి"),
    "Venus":   ("తెలుపు లేదా గులాబీ", 6, "శుక్రవారం లక్ష్మీదేవికి తామర పువ్వులు సమర్పించండి"),
    "Saturn":  ("నీలం లేదా నలుపు", 8, "శనివారం శనీశ్వరుడికి నువ్వుల నూనె దీపం వెలిగించండి"),
}
LUCKY_HI = {
    "Sun":     ("लाल या नारंगी", 1, "रविवार को सूर्य देव को सुबह जल चढ़ाएँ"),
    "Moon":    ("सफ़ेद या चाँदी जैसा", 2, "सोमवार को शिव जी का दूध से अभिषेक करें"),
    "Mars":    ("लाल", 9, "मंगलवार को हनुमान जी को सिंदूर चढ़ाएँ"),
    "Mercury": ("हरा", 5, "बुधवार को गणेश जी को दूर्वा चढ़ाएँ"),
    "Jupiter": ("पीला या सुनहरा", 3, "गुरुवार को विष्णु जी को पीले फूल चढ़ाएँ"),
    "Venus":   ("सफ़ेद या गुलाबी", 6, "शुक्रवार को लक्ष्मी जी को कमल चढ़ाएँ"),
    "Saturn":  ("नीला या काला", 8, "शनिवार को शनि देव को तिल के तेल का दीपक जलाएँ"),
}

# Telugu weekday names — Python weekday(): Monday=0 … Sunday=6
TELUGU_WEEKDAY = {
    0: "సోమవారం", 1: "మంగళవారం", 2: "బుధవారం", 3: "గురువారం",
    4: "శుక్రవారం", 5: "శనివారం", 6: "ఆదివారం",
}

# Words that mean "today" — a weekday name in the same sentence as one of
# these MUST be the actual day. (Day names elsewhere, e.g. remedies like
# "శుక్రవారం లక్ష్మీ పూజ", are legitimate and left untouched.)
_TODAY_WORDS = ("ఈరోజు", "ఈ రోజు", "నేడు")


def fix_weekday(text: str, correct_day: str) -> str:
    """Replace hallucinated weekday names in 'today' sentences."""
    if not text:
        return text
    import re
    parts = re.split(r"([।.!?\n])", text)
    out = []
    for seg in parts:
        if any(w in seg for w in _TODAY_WORDS):
            for wd in TELUGU_WEEKDAY.values():
                if wd != correct_day and wd in seg:
                    seg = seg.replace(wd, correct_day)
        out.append(seg)
    return "".join(out)


def fix_punctuation(text: str) -> str:
    """Give every sentence its own breath so the audio doesn't sound robotic.

    gTTS inserts a pause at '.', '!' and '?' but NOT at the Indic danda '।',
    and only when a SPACE follows the terminator. Models often end Telugu/Hindi
    sentences with a danda or glue the next sentence straight on ('...పోతుంది.మీకు'),
    so gTTS reads several sentences as one long run — the robotic feeling. We
    normalise the danda to a period and guarantee one space after each
    terminator. Captions benefit too (build_video re-wraps by word). Idempotent."""
    if not text:
        return text
    import re
    text = text.replace("॥", ". ").replace("।", ". ")   # danda -> period+space
    text = re.sub(r"\s*\n\s*", " ", text)               # newlines -> space (one audio stream)
    text = re.sub(r"\s+([.,!?;:])", r"\1", text)         # no space BEFORE punctuation
    text = re.sub(r"([.!?])(?=[^\s.!?])", r"\1 ", text)  # one space AFTER a sentence ender
    text = re.sub(r"(,)(?=\S)", r"\1 ", text)            # one space after a glued comma
    text = re.sub(r"[ \t]{2,}", " ", text)               # collapse doubled spaces
    return text.strip()


# Frozen ONCE on the first call, then reused for the whole run. This makes
# every video (all 12 Telugu + 12 Hindi) share the exact same date even if
# the run crosses IST midnight midway — otherwise the later-generated Hindi
# scripts could land on the next day. One process = one run = one date.
_TOMORROW_CACHE = None


def _ist_tomorrow() -> datetime.datetime:
    global _TOMORROW_CACHE
    if _TOMORROW_CACHE is None:
        _TOMORROW_CACHE = (datetime.datetime.now(ZoneInfo("Asia/Kolkata"))
                           + datetime.timedelta(days=1))
    return _TOMORROW_CACHE


def _get_ist_dates():
    tomorrow   = _ist_tomorrow()
    today_str  = tomorrow.strftime("%B %d, %Y")
    date_short = tomorrow.strftime("%b %d %Y")
    weekday_te = TELUGU_WEEKDAY[tomorrow.weekday()]
    return today_str, date_short, weekday_te

def _build_grounding_block(g: dict | None) -> str:
    """Format BPHS sutras from Supabase into a prompt section (empty if none)."""
    if not g:
        return ""
    lines = [
        "",
        f"CLASSICAL GROUNDING — Today's vara lord is {g['planet']} ({g['planet_te']}).",
        "Base the predictions on these authentic Parashara (BPHS) sutras. Adapt them "
        "into DAILY transit-style predictions — NEVER copy natal life-outcomes verbatim. "
        "Mention \"పరాశర మహర్షి ప్రకారం\" exactly once in the script for authority.",
    ]
    for i, s in enumerate(g["sutras"], 1):
        lines.append(f"Sutra {i}: {s}")
    if g.get("caution"):
        lines.append(
            f"Caution basis (soften into ONE mild 'జాగ్రత్త' tip, keep it gentle): {g['caution']}"
        )
    if g.get("remedy"):
        lines.append(
            f"Use THIS as today's remedy (classical Parashara remedy, adapt wording): {g['remedy']}"
        )
    return "\n".join(lines)


def _build_hooks_block(top_hooks: list[str] | None) -> str:
    """Feedback loop: steer the hook style toward recent top performers."""
    if not top_hooks:
        return ""
    lines = [
        "",
        "PROVEN HOOKS — these recent hooks got the MOST VIEWS. Write "
        "highlight_telugu with similar style and energy (do NOT copy them, "
        "today's prediction must be fresh):",
    ]
    for i, h in enumerate(top_hooks, 1):
        lines.append(f"{i}. {h}")
    return "\n".join(lines)


# ── Astroloz transit engine ──────────────────────────────────────────────────
# The real astrology is COMPUTED by the Astroloz backend (Swiss Ephemeris +
# classical gochara) at GET /api/v1/daily/transit/{rasi}. Groq stops inventing
# predictions and only phrases these facts. If the call fails for any reason we
# return None and the caller falls back to the original Groq-only path — the
# pipeline must never fail because the engine is down (see config
# "use_astroloz_engine").
ASTROLOZ_API_URL = os.environ.get("ASTROLOZ_API_URL", "https://api.astroloz.com").rstrip("/")


def _ord(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def fetch_daily_transit(sign: str, date_iso: str, timeout: int = 12) -> dict | None:
    """GET the computed gochara facts for one rasi. Returns None on ANY failure
    (unreachable, non-200, malformed) so the caller degrades to Groq-only."""
    url = f"{ASTROLOZ_API_URL}/api/v1/daily/transit/{sign}?date={date_iso}"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                raise ValueError(f"HTTP {resp.status}")
            data = json.loads(resp.read().decode("utf-8"))
        if not data.get("active_transits"):
            raise ValueError("response missing active_transits")
        return data
    except Exception as e:                       # noqa: BLE001 — any error -> fallback
        print(f"        ⚠ Astroloz engine unavailable for {sign} ({e}); "
              f"using Groq-only fallback")
        return None


def _build_transit_block(t: dict) -> str:
    """Format the computed gochara facts into an English facts block. Groq
    phrases ONLY these — it never adds a planet, house or effect of its own."""
    if not t:
        return ""
    lord = t.get("lucky", {}).get("rasi_lord")
    by_planet = {a["planet"]: a for a in t["active_transits"]}
    moon_effect = next((r["effect"] for r in t.get("bphs_rules_matched", [])
                        if r.get("rule_id") == "gochara-moon"), "")

    lines = [
        "",
        "COMPUTED TRANSITS (Astroloz engine — Swiss Ephemeris, sidereal Lahiri).",
        "These are the ONLY astrological facts you may use. Do NOT introduce any "
        "planet, house, nakshatra, transit, event or effect not listed here.",
        f"- Moon: in {t['moon_sign']} ({t['moon_nakshatra']} nakshatra), "
        f"{_ord(t['moon_house_from_rasi'])} from this rasi — {moon_effect}.",
    ]
    if t.get("chandrashtama"):
        lines.append("- CHANDRASHTAMA today for this rasi: the mind is unsettled; "
                     "advise postponing new commitments and travel.")
    if t.get("sade_sati", {}).get("active"):
        lines.append(f"- Sade Sati is ACTIVE ({t['sade_sati']['phase']} phase) — "
                     "patience and steady effort.")
    if lord and lord in by_planet:
        lt = by_planet[lord]
        lines.append(f"- Rasi lord {lord}: in {lt['sign']}, {_ord(lt['house_from_rasi'])} "
                     f"from the rasi ({'supportive' if lt['favourable'] else 'demanding'}, "
                     f"{lt['strength']}).")
    lines.append("- Key planet transits (house counted from this rasi):")
    for p in ("Sun", "Mars", "Jupiter", "Saturn", "Rahu", "Ketu"):
        a = by_planet.get(p)
        if a:
            lines.append(f"    {p}: {_ord(a['house_from_rasi'])} "
                         f"({'supportive' if a['favourable'] else 'demanding'}, {a['strength']})")
    lines.append("- Life-area outlook (derived from the transits above — phrase these):")
    for dom in ("career", "money", "love", "health"):
        d = t["domain_summary"].get(dom, {})
        lines.append(f"    {dom}: {d.get('tone', 'steady')} — {d.get('gist', '')}")
    c = t.get("caution", {})
    if c.get("active"):
        lines.append(f"- Risk/caution to voice as ONE gentle line: {c.get('reason')} "
                     f"→ {c.get('advice')}.")
    return "\n".join(lines)


def _call_groq(client, sign, languages, theme, tone, grounding=None,
               top_hooks=None, transit=None) -> list[dict]:
    today, date_short, weekday_te = _get_ist_dates()
    lang        = languages[0]
    rasi_telugu = RASI_TELUGU.get(sign, sign)
    symbol      = SIGN_SYMBOLS.get(sign, "🔮")

    # Per-sign daily ingredients — guarantee 12 DISTINCT videos per day
    lord    = RASI_LORD.get(sign, "")
    element = RASI_ELEMENT.get(sign, "")
    signs_order = list(RASI_TELUGU.keys())
    sign_idx    = signs_order.index(sign) if sign in signs_order else 0
    day_of_year = datetime.datetime.now(ZoneInfo("Asia/Kolkata")).timetuple().tm_yday
    focus       = FOCUS_ROTATION[(day_of_year + sign_idx) % len(FOCUS_ROTATION)]
    _luck_color, _luck_num, luck_remedy = LUCKY_TE.get(SIGN_PLANET.get(sign, "Sun"))

    # Engine mode (transit facts present): Groq PHRASES the computed transits and
    # invents nothing. Fallback (transit is None): the original invent-your-own
    # path, unchanged. Only the script directive + guidance block + temperature
    # differ between the two; everything else in the prompt is shared.
    engine_block = _build_transit_block(transit)
    if transit:
        script_directive = (
            f"250 word horoscope in pure Telugu script. FIRST SENTENCE = a shocking "
            f"curiosity hook about today's main focus ({focus}) for this rasi (viewers "
            f"decide to stay in 3 seconds) — NEVER start with a greeting like నమస్కారం "
            f"or 'ఈరోజు మీకు'. Then cover IN ORDER, phrasing ONLY the COMPUTED TRANSITS "
            f"above: {lord} position and its influence, career, money, love/family, "
            f"health, the ONE risk/caution given above, then the remedy EXACTLY as "
            f"specified below, then a one-line closing blessing."
        )
        guidance_block = (
            "GROUNDING RULE (most important): every astrological statement MUST trace to "
            "the COMPUTED TRANSITS block above — those real transits already differ per "
            f"rasi. Translate {rasi_telugu}'s transits into warm, natural, specific "
            "Telugu; never copy another rasi's wording, and never invent a prediction "
            "the facts do not support. Keep health gentle (no disease names, nothing "
            "frightening) and money non-committal (no guaranteed amounts)."
        )
        temperature = 0.6
    else:
        script_directive = (
            f"250 word horoscope in pure Telugu script. FIRST SENTENCE = a shocking "
            f"curiosity hook about today's main focus ({focus}) for this rasi (viewers "
            f"decide to stay in 3 seconds) — NEVER start with a greeting like నమస్కారం "
            f"or 'ఈరోజు మీకు'. Then cover in order: {lord} position and influence, "
            f"career, money, love/family, health, 1 risk warning, then the remedy "
            f"EXACTLY as specified below, then a one-line closing blessing."
        )
        guidance_block = f"""SPECIFICITY & ANTI-REPETITION (most important rule):
Every prediction must be SPECIFIC and ORIGINAL to {rasi_telugu} today. The notes below describe the STYLE in English — they are NOT text to translate or reuse. Write your OWN fresh Telugu sentences. Two different rasis must NEVER share the same health issue, the same money event, or the same love event on the same day — invent different concrete details each time.
- HEALTH: name a specific body part/condition + a concrete action (not "take care of health"). Pick an issue that fits {rasi_telugu}'s element ({element}) — do not default to throat/cold-food every time.
- MONEY: name a specific source or situation (a returned loan, a property decision, an afternoon overspend risk, a bonus, a family expense) — vary it.
- CAREER: name a specific work situation (praise from a senior, a new responsibility, a colleague friction, an interview, a transfer) — vary it.
- LOVE/FAMILY: name a specific person or event (spouse, child's news, a parent, an old friend, a proposal) — vary it.
Make it feel personally written by a real astrologer who is reading THIS rasi's chart, not a template."""
        temperature = 0.85

    prompt = f"""Vedic astrologer. For {sign} ({rasi_telugu}) on {today}. Theme of the day: {theme}. Tone: {tone}.

DAY FACT (do not get this wrong): {today} is {weekday_te}. If the script mentions today's weekday, it MUST be {weekday_te}. Day names for remedies on OTHER days are allowed (e.g. శుక్రవారం పూజ) but never claim today is a different day.

THIS RASI'S UNIQUE CONTEXT (must drive the whole reading):
- Rasi lord: {lord} — base the planetary reasoning on this lord's current influence.
- Element: {element}
- TODAY'S MAIN FOCUS for {rasi_telugu}: {focus} — the hook AND the strongest prediction must center on this focus.
CRITICAL: 12 rasis get videos on the same day. Families with members of different rasis watch them together — if predictions feel identical it destroys trust. Make this reading CLEARLY specific to {rasi_telugu}: different events, different areas of life, different remedies than any other rasi would get.
{_build_grounding_block(grounding)}{_build_hooks_block(top_hooks)}{engine_block}

Return ONLY this JSON object. Start with {{ end with }}. No text outside:
{{
  "sign": "{sign}",
  "rasi_telugu": "{rasi_telugu}",
  "language": "{lang['name']}",
  "language_code": "{lang['code']}",
  "highlight_telugu": "The single most distinctive prediction FROM script_telugu, rewritten as a dramatic hook — this is THIS video's THUMBNAIL AND TITLE. It must be about today's main focus ({focus}) and could not apply to any other rasi's video today. COMPLETE sentence of 5 to 8 words. Present tense. NO hedging words like 'maybe/might/possibly'.",
  "script_telugu": "{script_directive}",
  "title_en": "{sign} - {date_short} | Telugu Daily Horoscope"
}}

FIXED FACTS for this rasi (use these EXACT values, do not invent your own):
- Remedy (tied to rasi lord {lord}): {luck_remedy}
(This remedy comes from {rasi_telugu}'s ruling planet, so it differs from other rasis — always use it. Do NOT mention any lucky colour or lucky number anywhere in the script.)

{guidance_block}"""

    last_error = None
    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model=os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b"),
                messages=[
                    {
                        "role": "system",
                        "content": "Expert Vedic astrologer with 30 years of practice. Write ALL content in pure Telugu unicode script. Every prediction must be SPECIFIC with concrete details — specific body parts for health, specific money sources, specific work situations, specific family members, specific deities and days for remedies. NEVER generic one-liners. Return ONLY raw JSON starting with { ending with }. No markdown."
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                max_tokens=3000,
                response_format={"type": "json_object"},
            )

            raw = response.choices[0].message.content.strip()
            if "```" in raw:
                for part in raw.split("```"):
                    part = part.strip()
                    if part.startswith("json"):
                        part = part[4:].strip()
                    if part.startswith("{"):
                        raw = part
                        break

            start = raw.find("{")
            end   = raw.rfind("}") + 1
            if start == -1 or end <= 1:
                raise ValueError("No JSON object found")

            obj = json.loads(raw[start:end])

            required = ["sign", "script_telugu", "highlight_telugu", "title_en"]
            for key in required:
                if key not in obj or not obj[key]:
                    raise ValueError(f"Missing key: {key}")

            # Deterministic weekday correction — the LLM sometimes claims the
            # wrong day; fix any day name in "today" sentences to the real one.
            obj["script_telugu"]    = fix_weekday(obj["script_telugu"], weekday_te)
            obj["highlight_telugu"] = fix_weekday(obj["highlight_telugu"], weekday_te)
            # Normalise sentence punctuation so the audio breathes (see fix_punctuation).
            obj["script_telugu"]    = fix_punctuation(obj["script_telugu"])

            # Build spoken audio script.
            # Sentence 1 is now the HOOK, so the CTA goes after the SECOND
            # sentence boundary — hook lands 0-5s, CTA ~10s (matches the
            # 10-16s on-screen overlay). Never cuts mid-sentence.
            raw = obj["script_telugu"]
            boundaries = [i + 1 for i, ch in enumerate(raw)
                          if ch in ("।", ".", "?", "!")]
            cut = boundaries[1] if len(boundaries) >= 2 else (
                  boundaries[0] if boundaries else len(raw))
            head = raw[:cut].strip()
            tail = raw[cut:].strip()
            obj["script"] = fix_punctuation(
                head + " " + CTA_SPOKEN + (" " + tail if tail else "")
            )

            obj["rasi_telugu"] = obj.get("rasi_telugu", rasi_telugu)

            # Hook line as YouTube title (thumbnail text = title = one message)
            obj["title_yt"] = build_title(
                obj["highlight_telugu"], obj["rasi_telugu"], date_short
            )

            # Metadata for the performance feedback loop
            obj["planet"] = grounding["planet"] if grounding else None
            obj["theme"]  = theme
            return [obj]

        except json.JSONDecodeError as e:
            last_error = f"JSON error: {e}"
            print(f"        Attempt {attempt+1} failed: {last_error}")
            time.sleep(5)
        except ValueError as e:
            last_error = str(e)
            print(f"        Attempt {attempt+1} failed: {last_error}")
            time.sleep(5)
        except Exception as e:
            if "429" in str(e):
                print(f"        Rate limit, waiting 70s...")
                time.sleep(70)
                last_error = str(e)
            else:
                raise

    raise RuntimeError(f"Failed after 3 attempts for {sign}. Last: {last_error}")


def generate_scripts(config: dict, grounding: dict | None = None,
                     top_hooks: list[str] | None = None) -> list[dict]:
    client       = Groq(api_key=os.environ["GROQ_API_KEY"])
    signs        = config["signs"]
    languages    = config["languages"]
    theme        = config["daily_theme"]
    tone         = config["tone"]

    # Astroloz engine: compute the real transits, let Groq only phrase them.
    # Flip config "use_astroloz_engine" to false to fall back to Groq-only.
    use_engine = config.get("use_astroloz_engine", True)
    date_iso   = _ist_tomorrow().date().isoformat()
    if use_engine:
        print(f"  🪐 Astroloz transit engine ON — grounding on computed gochara "
              f"for {date_iso} ({ASTROLOZ_API_URL})")
    else:
        print("  🪐 Astroloz transit engine OFF (use_astroloz_engine=false) — Groq-only")

    all_scripts = []
    engine_used = 0
    for i, sign in enumerate(signs, 1):
        print(f"  → Sign {i}/{len(signs)}: {sign}...")
        transit = fetch_daily_transit(sign, date_iso) if use_engine else None
        if transit:
            engine_used += 1
        sign_grounding = grounding.get(sign) if grounding else None
        results = _call_groq(client, sign, languages, theme, tone,
                             sign_grounding, top_hooks, transit)
        all_scripts.extend(results)
        if i < len(signs):
            time.sleep(4)

    if use_engine:
        print(f"  ✓ Groq returned {len(all_scripts)} scripts total "
              f"({engine_used}/{len(signs)} grounded on the transit engine, "
              f"{len(signs) - engine_used} via Groq-only fallback)")
    else:
        print(f"  ✓ Groq returned {len(all_scripts)} scripts total")
    return all_scripts


# ═══════════════════════════════════════════════════════════════════════════
# HINDI PIPELINE (parallel to Telugu — separate so the working Telugu path is
# never touched). Items use the SAME dict keys as Telugu (rasi_telugu /
# highlight_telugu / script_telugu) so downstream build_video, tts_audio,
# post_instagram work unchanged; the discriminator is item["lang"] == "hi".
# ═══════════════════════════════════════════════════════════════════════════

CTA_SPOKEN_HI = (
    "अपनी निजी जन्मकुंडली से जुड़े सवालों के पूरे मुफ़्त जवाब के लिए "
    "link कमेंट करें। मैं वेबसाइट लिंक reply करूँगा।"
)

RASI_HINDI = {
    "Aries":"मेष राशि","Taurus":"वृषभ राशि","Gemini":"मिथुन राशि",
    "Cancer":"कर्क राशि","Leo":"सिंह राशि","Virgo":"कन्या राशि",
    "Libra":"तुला राशि","Scorpio":"वृश्चिक राशि","Sagittarius":"धनु राशि",
    "Capricorn":"मकर राशि","Aquarius":"कुंभ राशि","Pisces":"मीन राशि",
}
RASI_LORD_HI = {
    "Aries":"मंगल","Taurus":"शुक्र","Gemini":"बुध","Cancer":"चंद्र",
    "Leo":"सूर्य","Virgo":"बुध","Libra":"शुक्र","Scorpio":"मंगल",
    "Sagittarius":"गुरु (बृहस्पति)","Capricorn":"शनि","Aquarius":"शनि",
    "Pisces":"गुरु (बृहस्पति)",
}
RASI_ELEMENT_HI = {
    "Aries":"अग्नि","Leo":"अग्नि","Sagittarius":"अग्नि",
    "Taurus":"पृथ्वी","Virgo":"पृथ्वी","Capricorn":"पृथ्वी",
    "Gemini":"वायु","Libra":"वायु","Aquarius":"वायु",
    "Cancer":"जल","Scorpio":"जल","Pisces":"जल",
}
FOCUS_ROTATION_HI = [
    "करियर में बड़ा बदलाव", "अचानक धन लाभ", "प्रेम और विवाह",
    "स्वास्थ्य में मोड़", "पारिवारिक शुभ समाचार", "शिक्षा और प्रतियोगी परीक्षा",
    "व्यापार का अवसर", "यात्रा योग", "संपत्ति और वाहन",
    "आध्यात्मिक प्रगति", "पुराने मित्रों से मुलाकात", "नई शुरुआत",
]
HINDI_WEEKDAY = {
    0:"सोमवार", 1:"मंगलवार", 2:"बुधवार", 3:"गुरुवार",
    4:"शुक्रवार", 5:"शनिवार", 6:"रविवार",
}
_TODAY_WORDS_HI = ("आज",)


def _fix_weekday_hi(text: str, correct_day: str) -> str:
    """Correct hallucinated weekday names in Hindi 'today' sentences."""
    if not text:
        return text
    import re
    parts = re.split(r"([।.!?\n])", text)
    out = []
    for seg in parts:
        if any(w in seg for w in _TODAY_WORDS_HI):
            for wd in HINDI_WEEKDAY.values():
                if wd != correct_day and wd in seg:
                    seg = seg.replace(wd, correct_day)
        out.append(seg)
    return "".join(out)


def _call_groq_hindi(client, sign, theme, tone) -> list[dict]:
    today, date_short, _ = _get_ist_dates()
    tomorrow   = _ist_tomorrow()   # same frozen date as Telugu — immune to midnight crossing
    weekday_hi = HINDI_WEEKDAY[tomorrow.weekday()]

    rasi_hi = RASI_HINDI.get(sign, sign)
    lord    = RASI_LORD_HI.get(sign, "")
    element = RASI_ELEMENT_HI.get(sign, "")
    signs_order = list(RASI_HINDI.keys())
    sign_idx    = signs_order.index(sign) if sign in signs_order else 0
    day_of_year = tomorrow.timetuple().tm_yday
    focus       = FOCUS_ROTATION_HI[(day_of_year + sign_idx) % len(FOCUS_ROTATION_HI)]
    _luck_color, _luck_num, luck_remedy = LUCKY_HI.get(SIGN_PLANET.get(sign, "Sun"))

    prompt = f"""Vedic astrologer. For {sign} ({rasi_hi}) on {today}. Theme of the day: {theme}. Tone: {tone}.

DAY FACT (do not get this wrong): {today} is {weekday_hi}. If the script mentions today's weekday, it MUST be {weekday_hi}. Day names for remedies on OTHER days are allowed but never claim today is a different day.

THIS RASI'S UNIQUE CONTEXT (must drive the whole reading):
- Rasi lord (राशि स्वामी): {lord} — base the planetary reasoning on this lord's current influence.
- Element (तत्व): {element}
- TODAY'S MAIN FOCUS for {rasi_hi}: {focus} — the hook AND the strongest prediction must center on this focus.
CRITICAL: 12 rasis get videos the same day and families watch together — make this reading CLEARLY specific to {rasi_hi}, with different events/areas/remedies than any other rasi would get.

Return ONLY this JSON object. Start with {{ end with }}. No text outside:
{{
  "sign": "{sign}",
  "rasi_hindi": "{rasi_hi}",
  "highlight_hindi": "The single most distinctive prediction FROM script_hindi, rewritten as a dramatic hook in pure Hindi (Devanagari) — this is THIS video's THUMBNAIL AND TITLE, about today's focus ({focus}), and could not apply to any other rasi. COMPLETE sentence of 5 to 8 words. Present tense. NO hedging words.",
  "script_hindi": "250 word horoscope in pure Hindi (Devanagari script). FIRST SENTENCE = a shocking curiosity hook about today's focus ({focus}) — NEVER start with a greeting like नमस्ते. Then cover in order: {lord} position and influence, career (करियर), money (धन), love/family (प्रेम/परिवार), health (स्वास्थ्य), 1 risk warning, then the remedy EXACTLY as specified below, then a one-line closing blessing.",
  "title_en": "{sign} - {date_short} | Hindi Daily Horoscope"
}}

FIXED FACTS for this rasi (use these EXACT values, do not invent your own):
- Remedy (उपाय, tied to rasi lord {lord}): {luck_remedy}
(This remedy comes from {rasi_hi}'s ruling planet, so it differs from other rasis — always use it. Do NOT mention any lucky colour or lucky number anywhere in the script.)

SPECIFICITY & ANTI-REPETITION (most important rule):
Every prediction must be SPECIFIC and ORIGINAL to {rasi_hi} today. The notes below describe the STYLE in English — they are NOT text to translate or reuse. Write your OWN fresh Hindi sentences. Two different rasis must NEVER share the same health issue, money event, or love event on the same day — invent different concrete details each time.
- HEALTH: a specific body part/condition + a concrete action; pick one fitting {rasi_hi}'s element ({element}) — do not default to throat/cold-food every time.
- MONEY: a specific source/situation (returned loan, property decision, afternoon overspend, bonus, family expense) — vary it.
- CAREER: a specific work situation (praise from a senior, new responsibility, colleague friction, interview, transfer) — vary it.
- LOVE/FAMILY: a specific person/event (spouse, child's news, a parent, an old friend, a proposal) — vary it.
Make it feel personally written by a real astrologer reading THIS rasi's chart, not a template."""

    last_error = None
    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model=os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b"),
                messages=[
                    {"role": "system",
                     "content": "Expert Vedic astrologer with 30 years of practice. Write ALL content in pure Hindi (Devanagari) unicode script. Every prediction must be SPECIFIC with concrete details. NEVER generic one-liners. Return ONLY raw JSON starting with { ending with }. No markdown."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.85,
                max_tokens=3000,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content.strip()
            if "```" in raw:
                for part in raw.split("```"):
                    part = part.strip()
                    if part.startswith("json"):
                        part = part[4:].strip()
                    if part.startswith("{"):
                        raw = part
                        break
            start = raw.find("{"); end = raw.rfind("}") + 1
            if start == -1 or end <= 1:
                raise ValueError("No JSON object found")
            obj = json.loads(raw[start:end])
            for key in ("sign", "script_hindi", "highlight_hindi"):
                if not obj.get(key):
                    raise ValueError(f"Missing key: {key}")

            script_hi   = _fix_weekday_hi(obj["script_hindi"], weekday_hi)
            highlight_hi = _fix_weekday_hi(obj["highlight_hindi"], weekday_hi)
            script_hi   = fix_punctuation(script_hi)   # break danda-joined sentences

            # CTA after the 2nd sentence boundary (hook stays first)
            boundaries = [i + 1 for i, ch in enumerate(script_hi)
                          if ch in ("।", ".", "?", "!")]
            cut = boundaries[1] if len(boundaries) >= 2 else (
                  boundaries[0] if boundaries else len(script_hi))
            head = script_hi[:cut].strip()
            tail = script_hi[cut:].strip()
            audio_script = fix_punctuation(
                head + " " + CTA_SPOKEN_HI + (" " + tail if tail else ""))

            # Reuse the *_telugu key names so downstream code is unchanged;
            # they hold Hindi text and item["lang"]="hi" marks the language.
            return [{
                "sign":           sign,
                "lang":           "hi",
                "language":       "Hindi",
                "language_code":  "hi-IN",
                "rasi_telugu":    rasi_hi,        # holds Hindi rasi
                "highlight_telugu": highlight_hi, # holds Hindi hook
                "script_telugu":  script_hi,      # holds Hindi display script
                "script":         audio_script,   # Hindi audio (hook→CTA→rest)
                "title_yt":       build_title(highlight_hi, rasi_hi, date_short),
                "planet":         None,
                "theme":          theme,
            }]

        except json.JSONDecodeError as e:
            last_error = f"JSON error: {e}"; time.sleep(5)
        except ValueError as e:
            last_error = str(e); time.sleep(5)
        except Exception as e:
            if "429" in str(e):
                time.sleep(70); last_error = str(e)
            else:
                raise
    raise RuntimeError(f"Hindi failed after 3 attempts for {sign}. Last: {last_error}")


def generate_scripts_hindi(config: dict) -> list[dict]:
    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    signs  = config["signs"]
    theme  = config["daily_theme"]
    tone   = config["tone"]
    out = []
    for i, sign in enumerate(signs, 1):
        print(f"  → [HI] Sign {i}/{len(signs)}: {sign}...")
        out.extend(_call_groq_hindi(client, sign, theme, tone))
        if i < len(signs):
            time.sleep(4)
    print(f"  ✓ Groq returned {len(out)} Hindi scripts")
    return out
