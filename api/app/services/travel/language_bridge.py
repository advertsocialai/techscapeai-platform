"""
Language Bridge — Attack Point 1 from the strategy doc.

Translates between English and Indian languages (Hindi primarily) via Claude.
Provides clean stub responses so the platform is testable without a Claude key.
"""
from __future__ import annotations
import json
import logging
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

ANTHROPIC_URL     = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


SUPPORTED = {
    "en": "English", "hi": "Hindi", "ta": "Tamil", "te": "Telugu",
    "kn": "Kannada", "ml": "Malayalam", "mr": "Marathi", "bn": "Bengali",
    "gu": "Gujarati", "pa": "Punjabi", "ur": "Urdu",
}


def _stub_translate(text: str, target_lang: str) -> str:
    """Tiny heuristic dictionary so the demo flow works without a key."""
    if target_lang.startswith("hi"):
        # very small phrasebook
        table = {
            "hello":    "namaste",
            "thank you":"dhanyavaad",
            "please":   "kripaya",
            "where":    "kaha",
            "how much": "kitne ka",
            "yes":      "haan",
            "no":       "nahi",
            "taxi":     "taxi",
            "hotel":    "hotel",
            "water":    "paani",
            "food":     "khaana",
        }
        lower = text.lower()
        for en, hi in table.items():
            lower = lower.replace(en, hi)
        return f"[stub-hi] {lower}"
    if target_lang.startswith("en"):
        return f"[stub-en] {text}"
    return f"[stub-{target_lang}] {text}"


class LanguageBridge:
    def __init__(self) -> None:
        self.api_key = settings.ANTHROPIC_API_KEY
        self.model   = settings.AI_MODEL

    async def translate(
        self, *, text: str, source_lang: str = "auto",
        target_lang: str = "en", formality: str = "polite",
    ) -> dict:
        target = target_lang.lower().split("-")[0]
        if target not in SUPPORTED and target != "en":
            target = "en"

        if not self.api_key:
            return {
                "translated":  _stub_translate(text, target),
                "source_lang": source_lang,
                "target_lang": target,
                "model":       "stub",
            }

        prompt = (
            f"Translate the following message into {SUPPORTED.get(target, target)}. "
            f"Tone: {formality}. Preserve any names, numbers, dates exactly. "
            "Output ONLY the translation as a single line."
        )
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(
                ANTHROPIC_URL,
                headers={"x-api-key": self.api_key,
                         "anthropic-version": ANTHROPIC_VERSION,
                         "content-type": "application/json"},
                json={"model": self.model, "max_tokens": 400,
                      "system": prompt,
                      "messages": [{"role": "user", "content": text}]},
            )
            r.raise_for_status()
            data = r.json()

        translated = "".join(b.get("text", "") for b in data.get("content", [])
                              if b.get("type") == "text").strip()
        return {
            "translated":  translated,
            "source_lang": source_lang,
            "target_lang": target,
            "model":       self.model,
        }
