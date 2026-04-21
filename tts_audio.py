import requests
import base64
import os
import pathlib
import wave
import io

SARVAM_URL = "https://api.sarvam.ai/text-to-speech"
MAX_CHARS  = 490  # Sarvam limit is 500, keep buffer

SUPPORTED_CODES = {
    "te-IN", "hi-IN", "ta-IN", "kn-IN", "bn-IN", "mr-IN",
    "gu-IN", "ml-IN", "od-IN", "pa-IN"
}


def _split_text(text: str, max_chars: int = MAX_CHARS) -> list[str]:
    """Split text into chunks of max_chars, breaking at sentence boundaries."""
    # Split at sentence endings
    import re
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    chunks = []
    current = ""

    for sentence in sentences:
        if len(sentence) > max_chars:
            # Split long sentence at commas or spaces
            words = sentence.split()
            for word in words:
                if len(current) + len(word) + 1 > max_chars:
                    if current:
                        chunks.append(current.strip())
                    current = word
                else:
                    current = current + " " + word if current else word
        else:
            if len(current) + len(sentence) + 1 > max_chars:
                if current:
                    chunks.append(current.strip())
                current = sentence
            else:
                current = current + " " + sentence if current else sentence

    if current:
        chunks.append(current.strip())

    return [c for c in chunks if c]


def _call_sarvam(text: str, lang_code: str) -> bytes:
    """Call Sarvam TTS for a single chunk, return raw WAV bytes."""
    payload = {
        "inputs":               [text],
        "target_language_code": lang_code,
        "speaker":              "anushka",
        "pitch":                0,
        "pace":                 1.0,
        "loudness":             1.5,
        "speech_sample_rate":   22050,
        "enable_preprocessing": True,
        "model":                "bulbul:v2"
    }
    headers = {
        "api-subscription-key": os.environ["SARVAM_API_KEY"],
        "Content-Type":         "application/json"
    }
    r = requests.post(SARVAM_URL, json=payload, headers=headers, timeout=60)
    if not r.ok:
        print(f"        Sarvam error: {r.text[:200]}")
    r.raise_for_status()
    return base64.b64decode(r.json()["audios"][0])


def _join_wav_chunks(chunks: list[bytes]) -> bytes:
    """Concatenate multiple WAV byte arrays into one WAV file."""
    if len(chunks) == 1:
        return chunks[0]

    # Read all frames
    all_frames = b""
    params = None

    for chunk in chunks:
        with wave.open(io.BytesIO(chunk), 'rb') as wf:
            if params is None:
                params = wf.getparams()
            all_frames += wf.readframes(wf.getnframes())

    # Write combined WAV
    output = io.BytesIO()
    with wave.open(output, 'wb') as wf:
        wf.setparams(params)
        wf.writeframes(all_frames)

    return output.getvalue()


def synthesize(item: dict, out_dir: str) -> str:
    """
    Splits long script into 500-char chunks, calls Sarvam for each,
    joins audio chunks, saves as single .wav file.
    """
    lang_code = item["language_code"]
    if lang_code not in SUPPORTED_CODES:
        lang_code = "hi-IN"

    script = item["script"]
    chunks = _split_text(script)
    print(f"        ({len(chunks)} audio chunks)...")

    wav_chunks = []
    for i, chunk in enumerate(chunks):
        wav_bytes = _call_sarvam(chunk, lang_code)
        wav_chunks.append(wav_bytes)

    combined = _join_wav_chunks(wav_chunks)

    slug = f'{item["sign"]}_{item["language"]}'.replace(" ", "_").lower()
    path = pathlib.Path(out_dir) / f"{slug}.wav"
    path.write_bytes(combined)

    return str(path)
