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

    prompt = f"""Vedic astrologer. For {sign} rashi on {today}, write horoscope.

Return ONLY this JSON object (no extra text before or after):
{{
  "sign": "{sign}",
  "language": "{lang['name']}",
  "language_code": "{lang['code']}",
  "script_telugu": "Pure Telugu unicode. 250 words. Cover: active planet, career/money, love/family, health, 1 risk + remedy/prayer, lucky color+number, blessing.",
  "script_display": "Same content in Tenglish (Telugu words in English letters). 250 words.",
  "title_en": "{sign} - {date_short} | {lang['name']} Daily Horoscope"
}}"""

    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a Vedic astrologer. Return ONLY a raw JSON object. No text before or after the JSON. Start your response with { and end with }."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.8,
                max_tokens=4000,
            )
            break
        except Exception as e:
            if "429" in str(e) and attempt < 2:
                print(f"        Rate limit, waiting 70s...")
                time.sleep(70)
            else:
                raise

    raw = response.choices[0].message.content.strip()

    # Strip markdown fences
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    # Find JSON object boundaries
    start = raw.find("{")
    end   = raw.rfind("}") + 1

    if start == -1:
        raise ValueError(f"No JSON found. Got: {raw[:200]}")

    # If closing brace missing (truncated), attempt repair
    if end <= 1:
        print(f"  ⚠ Response truncated, attempting repair...")
        raw = raw[start:] + '"}'
        end = len(raw)

    try:
        obj = json.loads(raw[start:end])
    except json.JSONDecodeError:
        # Try to repair by finding last complete key-value
        chunk = raw[start:end]
        last_comma = chunk.rfind('",')
        if last_comma > 0:
            repaired = chunk[:last_comma+1] + '"dummy":"x"}'
            try:
                obj = json.loads(repaired)
            except:
                raise ValueError(f"Cannot parse JSON. Raw: {chunk[:300]}")
        else:
            raise

    obj["script"]         = obj.get("script_telugu", "") + " " + PROMO_TELUGU
    obj["script_display"] = obj.get("script_display", "") + " " + PROMO_TENGLISH

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
