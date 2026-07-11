import json
import os
import time
import datetime
from zoneinfo import ZoneInfo
from groq import Groq

# ── Conversion CTA — spoken (gTTS audio) ─────────────────────────────────────
# Inserted at a sentence boundary so it never cuts mid-sentence.
# Engagement CTA: viewers comment "link" → auto-reply delivers the website
# link (drives comment count, which the algorithm rewards).
CTA_SPOKEN = (
    "మీ విద్య, ఉద్యోగం, వ్యాపారం, వివాహం వంటి వ్యక్తిగత ప్రశ్నలకు పూర్తి "
    "ఉచిత సమాధానాల కోసం link అని comment చేయండి."
    " నేను website link reply ఇస్తాను."
)

# ── YouTube title — hook line as title (edit here) ───────────────────────────
# The dramatic highlight_telugu (same text as the 0-5s thumbnail card) becomes
# the title, so thumbnail and title reinforce each other. The suffix keeps the
# "రాశి ఫలాలు" search keyword. Total capped at 100 chars (YouTube hard limit);
# the highlight is truncated first, never the rasi/date suffix.
TITLE_SUFFIX_TEMPLATE = " | {rasi} ఫలాలు {date}"


def build_title(highlight: str, rasi: str, date_short: str) -> str:
    suffix = TITLE_SUFFIX_TEMPLATE.format(rasi=rasi, date=date_short)
    hl     = " ".join(highlight.split())          # collapse newlines/spaces
    max_hl = 100 - len(suffix)
    if len(hl) > max_hl:
        hl = hl[:max_hl - 1].rstrip() + "…"
    return hl + suffix

RASI_TELUGU = {
    "Aries":"మేష రాశి","Taurus":"వృషభ రాశి","Gemini":"మిథున రాశి",
    "Cancer":"కర్కాటక రాశి","Leo":"సింహ రాశి","Virgo":"కన్యా రాశి",
    "Libra":"తుల రాశి","Scorpio":"వృశ్చిక రాశి","Sagittarius":"ధనుస్సు రాశి",
    "Capricorn":"మకర రాశి","Aquarius":"కుంభ రాశి","Pisces":"మీన రాశి",
}

SIGN_SYMBOLS = {
    "Aries":"♈","Taurus":"♉","Gemini":"♊","Cancer":"♋",
    "Leo":"♌","Virgo":"♍","Libra":"♎","Scorpio":"♏",
    "Sagittarius":"♐","Capricorn":"♑","Aquarius":"♒","Pisces":"♓"
}

def _get_ist_dates():
    ist_now    = datetime.datetime.now(ZoneInfo("Asia/Kolkata"))
    tomorrow   = ist_now + datetime.timedelta(days=1)
    today_str  = tomorrow.strftime("%B %d, %Y")
    date_short = tomorrow.strftime("%b %d %Y")
    return today_str, date_short

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


def _call_groq(client, sign, languages, theme, tone, grounding=None,
               top_hooks=None) -> list[dict]:
    today, date_short = _get_ist_dates()
    lang        = languages[0]
    rasi_telugu = RASI_TELUGU.get(sign, sign)
    symbol      = SIGN_SYMBOLS.get(sign, "🔮")

    prompt = f"""Vedic astrologer. For {sign} ({rasi_telugu}) on {today}. Theme of the day: {theme}. Tone: {tone}.
{_build_grounding_block(grounding)}{_build_hooks_block(top_hooks)}

Return ONLY this JSON object. Start with {{ end with }}. No text outside:
{{
  "sign": "{sign}",
  "rasi_telugu": "{rasi_telugu}",
  "language": "{lang['name']}",
  "language_code": "{lang['code']}",
  "highlight_telugu": "ONE dramatic, exciting prediction in pure Telugu script — this is the VIDEO THUMBNAIL AND TITLE, it must stop the scroll. MUST be a COMPLETE sentence of 5 to 8 words (never fewer than 5). Present tense. NO hedging words like 'maybe/might/possibly'. Make viewers desperate to know more.",
  "script_telugu": "250 word horoscope in pure Telugu script. FIRST SENTENCE = a shocking curiosity hook about today's single biggest event for this rasi (viewers decide to stay in 3 seconds) — NEVER start with a greeting like నమస్కారం or 'ఈరోజు మీకు'. Then cover in order: active planet position, career, money, love/family, health, 1 risk warning, 1 remedy, lucky color + lucky number, one-line closing blessing.",
  "title_en": "{sign} - {date_short} | Telugu Daily Horoscope"
}}

SPECIFICITY RULES for script_telugu — every prediction must be SPECIFIC with concrete details. NEVER write generic one-line predictions:
- HEALTH: name a specific body part or condition + a concrete action. Like "గొంతు సంబంధిత సమస్యలు వచ్చే అవకాశం ఉంది, చల్లని పదార్థాలు తగ్గించండి" or "కంటి ఒత్తిడి పెరగవచ్చు, స్క్రీన్ సమయం తగ్గించండి". NOT "ఆరోగ్యం జాగ్రత్త".
- MONEY: name the specific source or situation. Like "పాత బాకీలు తిరిగి వస్తాయి" or "రియల్ ఎస్టేట్ పెట్టుబడికి అనుకూల సమయం" or "అనవసర ఖర్చులు మధ్యాహ్నం తర్వాత జాగ్రత్త". NOT "ధన లాభం".
- CAREER: name the specific work situation. Like "పై అధికారుల నుండి ప్రశంసలు లభిస్తాయి" or "కొత్త ప్రాజెక్ట్ బాధ్యత మీకు అప్పగించబడుతుంది" or "సహోద్యోగులతో మాట పట్టింపులకు పోవద్దు". NOT "ఉద్యోగంలో మంచి రోజు".
- LOVE/FAMILY: name the specific person or event. Like "జీవిత భాగస్వామి మద్దతుతో ఒక ముఖ్యమైన సమస్య నుండి బయటపడతారు" or "పిల్లల చదువు విషయంలో శుభవార్త వింటారు". NOT "కుటుంబం బాగుంటుంది".
- REMEDY: name a specific deity + day + action. Like "మంగళవారం ఆంజనేయస్వామికి సింధూరం సమర్పించండి" or "శుక్రవారం లక్ష్మీ దేవికి తామర పువ్వులు సమర్పించండి". NOT "దేవుడిని ప్రార్థించండి".
Vary the specifics daily so each day feels fresh and personally written by a real astrologer."""

    last_error = None
    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {
                        "role": "system",
                        "content": "Expert Vedic astrologer with 30 years of practice. Write ALL content in pure Telugu unicode script. Every prediction must be SPECIFIC with concrete details — specific body parts for health, specific money sources, specific work situations, specific family members, specific deities and days for remedies. NEVER generic one-liners. Return ONLY raw JSON starting with { ending with }. No markdown."
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.85,
                max_tokens=3000,
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
            obj["script"] = (
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
    all_scripts = []
    for i, sign in enumerate(signs, 1):
        print(f"  → Sign {i}/{len(signs)}: {sign}...")
        sign_grounding = grounding.get(sign) if grounding else None
        results = _call_groq(client, sign, languages, theme, tone,
                             sign_grounding, top_hooks)
        all_scripts.extend(results)
        if i < len(signs):
            time.sleep(4)

    print(f"  ✓ Groq returned {len(all_scripts)} scripts total")
    return all_scripts
