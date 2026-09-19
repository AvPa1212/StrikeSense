"""Coaching feedback. Gemini writes it when GEMINI_API_KEY is set; otherwise a rule-based
coach picks the biggest weighted gap and explains it. ElevenLabs speaks it when a key is set,
and the dashboard falls back to the browser's speech synthesis when it is not."""
from __future__ import annotations

import httpx

from config import (ELEVENLABS_API_KEY, ELEVENLABS_MODEL, ELEVENLABS_VOICE_ID, GEMINI_API_KEY,
                    GEMINI_MODEL)
from technique import LABELS

ADVICE = {
    "contact_vert": {
        "high": "You met the ball above its middle, which pushes it down and adds topspin. Lean back a little and strike through the center.",
        "low": "You met the ball below its middle, which lifts it and adds backspin. Keep your knee over the ball and strike through the center.",
    },
    "contact_lat": {
        "high": "Contact landed on the left side of the ball compared with the benchmark. Adjust your approach angle so the foot meets the center line.",
        "low": "Contact landed on the right side of the ball compared with the benchmark. Adjust your approach angle so the foot meets the center line.",
    },
    "topspin_dps": {
        "high": "There was more topspin than the benchmark. Get your chest back over the ball less and follow through lower.",
        "low": "There was less topspin than the benchmark. Strike a little higher on the ball and follow through over it.",
    },
    "sidespin_dps": {
        "high": "The ball curled more than the benchmark. Bring your swing path closer to straight through the target.",
        "low": "The ball curled less than the benchmark. Wrap the foot around the ball and finish across your body.",
    },
    "contact_ms": {
        "high": "The ball stayed on your foot longer than the benchmark. Lock the ankle earlier for a crisper strike.",
        "low": "Contact was quicker than the benchmark. Soften the ankle and guide the ball through for control.",
    },
    "hang_ms": {
        "high": "The ball stayed in the air longer than the benchmark. Keep your chest over the ball to flatten the flight.",
        "low": "The ball stayed in the air shorter than the benchmark. Lean back slightly and lift through the lower half of the ball.",
    },
    "speed_ms": {
        "high": "The ball left faster than the benchmark for this technique. Ease off if accuracy matters more than pace.",
        "low": "The ball left slower than the benchmark. Drive the hips through and land the foot firmly at contact.",
    },
    "launch_angle_deg": {
        "high": "The launch angle was higher than the benchmark. Lower your follow through.",
        "low": "The launch angle was lower than the benchmark. Get under the ball a little more.",
    },
}

DRILL = {
    "drive": "Drill: ten laces-only strikes at a wall from eight meters, eyes on the ball at contact.",
    "curl": "Drill: ten curled passes around a cone from twelve meters, wrapping the inside of the foot.",
    "chip": "Drill: ten chips over a bib at five meters, sliding the foot under the ball.",
    "pass": "Drill: twenty inside-foot passes between two cones, keeping the ankle locked.",
    "knuckle": "Drill: ten strikes with no follow through, hitting the valve area dead center.",
}


def _worst(score: dict):
    best = None
    for m in score["metrics"]:
        if not m["available"]:
            continue
        gap = m["weight"] * (100 - m["score"])
        if best is None or gap > best[0]:
            best = (gap, m)
    return best[1] if best else None


def rule_based(kick: dict) -> str:
    score = kick["score"]
    tech = kick["technique"]
    parts = []
    if kick["target"] != "auto" and kick["predicted"] != kick["target"] and kick["confidence"] > 0.6:
        parts.append(f"You aimed for a {LABELS[kick['target']].lower()}, but this read as a "
                     f"{LABELS[kick['predicted']].lower()}.")
    overall = score["overall"]
    if overall >= 85:
        parts.append(f"Strong {LABELS[tech].lower()}, {overall:.0f} out of 100.")
    else:
        parts.append(f"{LABELS[tech]} scored {overall:.0f} out of 100.")
        w = _worst(score)
        if w:
            side = "high" if w["z"] > 0 else "low"
            parts.append(ADVICE[w["key"]][side])
    parts.append(DRILL[tech])
    return " ".join(parts)


def _prompt(kick: dict) -> str:
    lines = []
    for m in kick["score"]["metrics"]:
        if m["available"]:
            lines.append(f"- {m['label']}: {m['value']} {m['unit']} (benchmark {m['target']:.2f}, "
                         f"match {m['score']:.0f}/100)")
    return (
        "You are a concise soccer striking coach reading data from a sensor ball. "
        f"The player aimed for: {kick['target']}. The network classified the kick as: {kick['predicted']} "
        f"({kick['confidence']:.0%}). Overall match to the benchmark: {kick['score']['overall']:.0f}/100.\n"
        + "\n".join(lines)
        + "\nWrite exactly three short sentences: what went well, the single biggest fix and why, "
          "and one drill. Plain language, no jargon, no em dashes, no lists."
    )


async def gemini_feedback(kick: dict) -> str | None:
    if not GEMINI_API_KEY:
        return None
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    body = {"contents": [{"parts": [{"text": _prompt(kick)}]}],
            "generationConfig": {"temperature": 0.6, "maxOutputTokens": 220}}
    try:
        async with httpx.AsyncClient(timeout=12) as c:
            r = await c.post(url, json=body, headers={"x-goog-api-key": GEMINI_API_KEY})
            r.raise_for_status()
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            return text.replace("\u2014", ", ").replace("\u2013", "-") or None
    except Exception:
        return None


async def feedback(kick: dict) -> dict:
    text = await gemini_feedback(kick)
    if text:
        return {"text": text, "source": "gemini"}
    return {"text": rule_based(kick), "source": "rules"}


async def speak(text: str) -> bytes | None:
    if not ELEVENLABS_API_KEY:
        return None
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(url, headers={"xi-api-key": ELEVENLABS_API_KEY,
                                           "Accept": "audio/mpeg"},
                             json={"text": text, "model_id": ELEVENLABS_MODEL})
            r.raise_for_status()
            return r.content
    except Exception:
        return None
