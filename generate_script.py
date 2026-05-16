import json
import os
import time
import datetime
from zoneinfo import ZoneInfo
from groq import Groq

PROMO_TELUGU = "వ్యక్తిగత రాశి సందేహాల కోసం, చానల్ డిస్క్రిప్షన్ లో ఉన్న Astroverse యాప్ లింక్ డౌన్లోడ్ చేసుకోండి."

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
    """Return tomorrow's date in IST (for next-day scheduling)."""
    ist_now      = datetime.datetime.now(ZoneInfo("Asia/Kolkata"))
    tomorrow     = ist_now + datetime.timedelta(days=1)
    today_str    = tomorrow.strftime("%B %d, %Y")
    date_short   = tomorrow.strftime("%b %d %Y")
    return today_str, date_short

def _call_groq(client, sign, languages, theme, tone) -> list[dict]:
    today, date_short = _get_ist_dates()
    lang         = languages[0]
    rasi_telugu  = RASI_TELUGU.get(sign, sign)
    symbol       = SIGN_SYMBOLS.get(sign, "🔮")

    prompt = f"""Vedic astrologer. For {sign} ({rasi_telugu}) on {today}.

Return ONLY this JSON. Start with {{ end with }}. No text outside:
{{
  "sign": "{sign}",
  "rasi_telugu": "{rasi_telugu}",
  "language": "{lang['name']}",
  "language_code": "{lang['code']}",
  "highlight_telugu": "Single most positive powerful statement in pure Telugu script for {sign} on {today}. Like: మేష రాశి వారికి ఈరోజు గొప్ప ధన లాభం కలుగుతుంది. Max 12 words. Must be in Telugu script. Must be most exciting positive thing happening today.",
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
                        "content": "Expert Vedic astrologer. Write ALL content in pure Telugu unicode script (తెలుగు). Return ONLY raw JSON starting with { ending with }. No markdown."
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

            obj["script"]        = obj["script_telugu"] + " " + PROMO_TELUGU
            obj["rasi_telugu"]   = obj.get("rasi_telugu", rasi_telugu)
            obj["title_en"]      = obj.get("title_en", f"{sign} - {date_short} | Telugu Daily Horoscope")

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
    client    = Groq(api_key=os.environ["GROQ_API_KEY"])
    signs     = config["signs"]
    languages = config["languages"]
    theme     = config["daily_theme"]
    tone      = config["tone"]

    all_scripts = []
    for i, sign in enumerate(signs, 1):
        print(f"  → Sign {i}/{len(signs)}: {sign}...")
        results = _call_groq(client, sign, languages, theme, tone)
        all_scripts.extend(results)
        if i < len(signs):
            time.sleep(4)

    print(f"  ✓ Groq returned {len(all_scripts)} scripts total")
    return all_scripts
