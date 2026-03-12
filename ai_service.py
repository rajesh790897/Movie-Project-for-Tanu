"""Helpers for generating recommendation copy with Gemini."""

from __future__ import annotations

import json
import os
from typing import Any

try:
    import google.generativeai as genai
except ImportError:  # pragma: no cover - handled at runtime if dependency is absent
    genai = None


DEFAULT_MODEL = "gemini-1.5-flash"


def gemini_enabled() -> bool:
    """Return True when the Gemini SDK is installed and an API key is set."""
    return bool(genai and os.getenv("GEMINI_API_KEY", "").strip())


def _clean_json_response(text: str) -> str:
    """Strip markdown code fences from model output before JSON parsing."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
    if cleaned.endswith("```"):
        cleaned = cleaned.rsplit("```", 1)[0]
    return cleaned.strip()


def generate_recommendation_story(
    seed_movie: dict[str, Any],
    preferences: dict[str, Any],
    recommendations: list[dict[str, Any]],
) -> dict[str, Any]:
    """Generate a short summary and per-movie reasons using Gemini."""
    if not gemini_enabled() or not recommendations:
        return {"enabled": False, "summary": "", "reasons": {}}

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    model_name = os.getenv("GEMINI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    genai.configure(api_key=api_key)

    prompt = {
        "task": (
            "You are helping a movie recommendation website explain why these live "
            "recommendations fit the user. Respond with strict JSON only."
        ),
        "output_schema": {
            "summary": "string, max 2 sentences",
            "reasons": {
                "movie title": "string, max 1 sentence"
            },
        },
        "seed_movie": seed_movie,
        "user_preferences": preferences,
        "recommendations": recommendations,
        "constraints": [
            "Do not use markdown.",
            "Keep tone concise and natural.",
            "Only mention facts supported by provided movie metadata.",
        ],
    }

    try:
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(
            json.dumps(prompt, ensure_ascii=True),
            generation_config={"temperature": 0.4},
        )
        raw_text = getattr(response, "text", "") or ""
        parsed = json.loads(_clean_json_response(raw_text))
    except Exception:
        return {"enabled": False, "summary": "", "reasons": {}}

    summary = str(parsed.get("summary", "")).strip()
    reasons = parsed.get("reasons", {})
    if not isinstance(reasons, dict):
        reasons = {}

    normalised_reasons = {
        str(title).strip(): str(reason).strip()
        for title, reason in reasons.items()
        if str(title).strip() and str(reason).strip()
    }

    return {
        "enabled": True,
        "summary": summary,
        "reasons": normalised_reasons,
        "model": model_name,
    }