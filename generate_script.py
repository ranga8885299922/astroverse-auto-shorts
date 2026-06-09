import json
import os
import time
import datetime
from zoneinfo import ZoneInfo
from groq import Groq

# ── Conversion CTA — spoken (gTTS audio) ─────────────────────────────────────
# Inserted after the first ~1/6 of horoscope words so it lands ~10-15 s in,
# before viewers drop off.  Write "dot com" so gTTS pronounces it clearly.
CTA_SPOKEN = (
    "మీ పూర్తి జాతకం, lucky time astroloz dot com లో ఉచితంగా చూడండి."
)

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

def _call_groq(client, sign, languages, theme, tone, promo_telugu) -> list[dict]:
    today, date_short = _get_ist_dates()
    lang        = languages[0]
    rasi_telugu = RASI_TELUGU.get(sign, sign)
    symbol      = SIGN_SYMBOLS.get(sign, "🔮")

    prompt = f"""Vedic astrologer. For {sign} ({rasi_telugu}) on {today}.

Return ONLY this JSON object. Start with {{ end with }}. No text outside:
{{
  "sign": "{sign}",
  "rasi_telugu": "{rasi_telugu}",
  "language": "{lang['name']}",
  "language_code": "{lang['code']}",
  "highlight_telugu": "Single most positive powerful statement in pure Telugu script for {sign} on {today}. Max 12 words. Must be Telugu script. Most exciting positive thing today.",
  "script_telugu": "Write 250 word horoscope in pure Telugu script. Cover: active planet, career, money, love, health, 1 risk + prayer remedy, lucky color+number, closing blessing.",
  "title_en": "{sign} - {date_short} | Telugu Daily Horoscope"
}}"""

    last_error = None
    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {
                        "role": "system",
                        "content": "Expert Vedic astrologer. Write ALL content in pure Telugu unicode script. Return ONLY raw JSON starting with { ending with }. No markdown."
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
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

            # Build spoken audio script:
            # 1. Insert early CTA after first ~1/6 of horoscope words (~10-15 s mark)
            # 2. Append end-of-video promo from config
            raw_words = obj["script_telugu"].split()
            split_at  = max(1, len(raw_words) // 6)
            script = (
                " ".join(raw_words[:split_at])
                + " " + CTA_SPOKEN
                + " " + " ".join(raw_words[split_at:])
            )
            if promo_telugu:
                script = script + " " + promo_telugu
            obj["script"] = script

            obj["rasi_telugu"] = obj.get("rasi_telugu", rasi_telugu)
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


def generate_scripts(config: dict) -> list[dict]:
    client       = Groq(api_key=os.environ["GROQ_API_KEY"])
    signs        = config["signs"]
    languages    = config["languages"]
    theme        = config["daily_theme"]
    tone         = config["tone"]
    promo_telugu = config.get("promo_telugu", "")  # Read from config

    all_scripts = []
    for i, sign in enumerate(signs, 1):
        print(f"  → Sign {i}/{len(signs)}: {sign}...")
        results = _call_groq(client, sign, languages, theme, tone, promo_telugu)
        all_scripts.extend(results)
        if i < len(signs):
            time.sleep(4)

    print(f"  ✓ Groq returned {len(all_scripts)} scripts total")
    return all_scripts
