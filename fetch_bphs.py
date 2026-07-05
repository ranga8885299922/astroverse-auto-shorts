"""
fetch_bphs.py — Ground daily predictions in the Parashara (BPHS) rules DB.

Concept: every weekday has a Vedic ruling planet (vara lord). We fetch that
planet's BPHS rules (Telugu translations) + the classical Parashara remedy
for that planet from Supabase, rotate them deterministically per sign per
date, and pass them to the LLM as grounding. The LLM adapts them into
daily-transit style predictions citing "పరాశర మహర్షి ప్రకారం".

SAFETY: BPHS natal rules include dire life outcomes (death, disease, loss
of child). Those must NEVER appear in a daily short. Rules whose English
effect matches the blocklist are dropped; remaining negatives are only
used as mild caution grounding.

Config via env (all optional — returns None if missing, pipeline runs
exactly as before):
  SUPABASE_URL          e.g. https://xxxx.supabase.co
  SUPABASE_SERVICE_KEY  service-role key (read access to rules tables)
"""

import os
import json
import random
import datetime
from zoneinfo import ZoneInfo

import requests

# Vedic vara (weekday) lords — Python weekday(): Monday=0 … Sunday=6
WEEKDAY_LORD = {
    0: "Moon", 1: "Mars", 2: "Mercury", 3: "Jupiter",
    4: "Venus", 5: "Saturn", 6: "Sun",
}

PLANET_TELUGU = {
    "Sun": "సూర్యుడు", "Moon": "చంద్రుడు", "Mars": "కుజుడు",
    "Mercury": "బుధుడు", "Jupiter": "గురువు", "Venus": "శుక్రుడు",
    "Saturn": "శని", "Rahu": "రాహువు", "Ketu": "కేతువు",
}

# Rules whose English effect contains any of these are never used
BLOCKLIST = [
    "death", "die", "demise", "corpse", "funeral", "short life",
    "lose his", "loss of child", "destruction", "widow", "dumb",
    "blind", "deaf", "impotent", "barren", "not be fertile",
    "disease", "leprosy", "insane", "lunatic", "imprison", "jail",
    "accident", "amputat", "suicide", "poison",
]

RULES_PER_SIGN     = 3   # positive grounding sutras per sign
CAUTIONS_PER_SIGN  = 1   # mild caution sutras per sign
FETCH_LIMIT        = 300


def _blocked(effect_english: str) -> bool:
    text = (effect_english or "").lower()
    return any(w in text for w in BLOCKLIST)


def _flatten(effect) -> str:
    """effects/translations are stored as JSON arrays of strings."""
    if isinstance(effect, str):
        try:
            parsed = json.loads(effect)
            if isinstance(parsed, list):
                return " ".join(str(p) for p in parsed)
        except (ValueError, TypeError):
            pass
        return effect
    if isinstance(effect, list):
        return " ".join(str(p) for p in effect)
    return str(effect)


def fetch_bphs_grounding(signs: list[str]) -> dict | None:
    """
    Returns {sign: {"planet", "planet_te", "sutras": [...], "caution": str|None,
    "remedy": str|None}} or None when Supabase is not configured/reachable.
    """
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        print("      (BPHS grounding skipped — SUPABASE_URL/KEY not set)")
        return None

    # The shorts are generated for TOMORROW (IST) — use tomorrow's vara lord
    tomorrow = datetime.datetime.now(ZoneInfo("Asia/Kolkata")) + datetime.timedelta(days=1)
    planet   = WEEKDAY_LORD[tomorrow.weekday()]
    headers  = {"apikey": key, "Authorization": f"Bearer {key}"}

    try:
        # Rules for the vara lord that HAVE a Telugu translation
        r = requests.get(
            f"{url}/rest/v1/astrology_rules",
            headers=headers,
            params={
                "select": "id,rule_type,is_positive,effects_english,"
                          "rule_translations!inner(translation)",
                "planet": f"eq.{planet}",
                "rule_translations.language": "eq.telugu",
                "limit": str(FETCH_LIMIT),
            },
            timeout=30,
        )
        r.raise_for_status()
        rules = r.json()

        # Classical Parashara remedy for the planet (Telugu)
        rem = requests.get(
            f"{url}/rest/v1/bphs_remedies",
            headers=headers,
            params={"select": "remedy_text",
                    "planet": f"eq.{planet}",
                    "language": "eq.telugu"},
            timeout=30,
        )
        rem.raise_for_status()
        remedies = [row["remedy_text"] for row in rem.json() if row.get("remedy_text")]
    except Exception as e:
        print(f"      (BPHS grounding skipped — fetch failed: {e})")
        return None

    positives, cautions = [], []
    for rule in rules:
        if _blocked(rule.get("effects_english", "")):
            continue
        translations = rule.get("rule_translations") or []
        if not translations:
            continue
        text = _flatten(translations[0].get("translation", "")).strip()
        if not text:
            continue
        (positives if rule.get("is_positive") else cautions).append(text)

    if not positives:
        print(f"      (BPHS grounding skipped — no usable rules for {planet})")
        return None

    print(f"      ✓ BPHS grounding: {planet} — {len(positives)} positive / "
          f"{len(cautions)} caution sutras, {len(remedies)} remedies")

    grounding = {}
    date_key  = tomorrow.strftime("%Y-%m-%d")
    for sign in signs:
        rng = random.Random(f"{date_key}:{sign}")   # deterministic daily rotation
        grounding[sign] = {
            "planet":    planet,
            "planet_te": PLANET_TELUGU.get(planet, planet),
            "sutras":    rng.sample(positives, min(RULES_PER_SIGN, len(positives))),
            "caution":   rng.choice(cautions) if cautions else None,
            "remedy":    rng.choice(remedies) if remedies else None,
        }
    return grounding
