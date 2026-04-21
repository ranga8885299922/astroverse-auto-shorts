import json
import os
import time
import datetime
from groq import Groq


PROMO_TELUGU = "Vyaktiga mee rashiki sambandhinchina prashnalanki samadhana kosam, channel description lo unna Astroverse app link download chesukondi. Mee jeevitam lo velugu teche jyotishyam ippudu mee chetilo undi."

PROMO_TENGLISH = "Vyaktiga mee rashiki sambandhinchina prashnalanki samadhana kosam, channel description lo unna Astroverse app link download chesukondi."


def _call_groq(client, sign, languages, theme, tone) -> list[dict]:
    today      = datetime.date.today().strftime("%B %d, %Y")
    date_short = datetime.date.today().strftime("%b %d %Y")
    lang       = languages[0]

    prompt = f"""You are an expert Vedic astrologer. For {sign} rashi on {today}, generate TWO versions of a horoscope.

Return this exact JSON:
{{
  "sign": "{sign}",
  "language": "{lang['name']}",
  "language_code": "{lang['code']}",
  "script_telugu": "PURE TELUGU script in Telugu unicode characters (తెలుగు లిపి). Min 300 words. Cover: today's active planet, career/money, love/family, health, 1 risk + specific remedy/prayer, lucky color+number, closing blessing. Warm and personal.",
  "script_display": "SAME content but written in Tenglish — Telugu language words spelled in English letters only. No English words. Min 300 words. Same sections as script_telugu.",
  "title_en": "{sign} - {date_short} | {lang['name']} Daily Horoscope"
}}

Only raw JSON. No markdown."""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "system",
                "content": "Expert Vedic astrologer. Return only raw JSON with two script versions: pure Telugu unicode and Tenglish romanized."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.8,
        max_tokens=6000,
    )

    raw = response.choices[0].message.content.strip()

    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    start = raw.find("{")
    end   = raw.rfind("}") + 1
    if start == -1 or end <= 1:
        raise ValueError(f"No JSON found. Got: {raw[:200]}")

    obj = json.loads(raw[start:end])

    # script = Telugu for Sarvam voice (with Telugu promo appended)
    # script_display = Tenglish for on-screen text
    obj["script"]         = obj.get("script_telugu", "") + " " + PROMO_TELUGU
    obj["script_display"] = obj.get("script_display", obj["script"]) + " " + PROMO_TENGLISH

    return [obj]


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
