"""Gemini provider (free tier via Google AI Studio).

Uses a constrained prompt + JSON response schema so the model can only emit
values from our fixed vocabulary. Any deviation is rejected by parse_llm_json,
and the router falls back. The model reasons about *diagnosis and play choice*;
it is never shown, and never emits, a rupee amount that reaches money.
"""
from __future__ import annotations

import json

import httpx

from .base import Diagnosis, parse_llm_json
from ..config import settings
from ..enums import Play, RootCause

_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

_SYSTEM = (
    "You are the diagnosis step of a payments recovery agent. Given a failed "
    "payment, classify the root cause and propose ONE recovery play. You output "
    "strict JSON only. You never compute money; a downstream deterministic engine "
    "owns all amounts. proposed_incentive_pct is only a suggestion.\n"
    f"root_cause must be one of: {[c.value for c in RootCause]}\n"
    f"proposed_play must be one of: {[p.value for p in Play]}\n"
)

_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "root_cause": {"type": "string", "enum": [c.value for c in RootCause]},
        "proposed_play": {"type": "string", "enum": [p.value for p in Play]},
        "proposed_incentive_pct": {"type": "integer"},
        "rationale": {"type": "string"},
    },
    "required": ["root_cause", "proposed_play", "proposed_incentive_pct", "rationale"],
}


class GeminiProvider:
    name = "gemini"

    def __init__(self) -> None:
        self._key = settings.gemini_api_key
        self._model = settings.gemini_model

    def available(self) -> bool:
        return bool(self._key)

    def diagnose(self, features: dict) -> Diagnosis:
        url = _ENDPOINT.format(model=self._model)
        body = {
            "system_instruction": {"parts": [{"text": _SYSTEM}]},
            "contents": [{"parts": [{"text": "Failed payment features:\n" + json.dumps(features)}]}],
            "generationConfig": {
                "temperature": 0.2,
                "response_mime_type": "application/json",
                "response_schema": _RESPONSE_SCHEMA,
            },
        }
        resp = httpx.post(
            url, params={"key": self._key}, json=body, timeout=20.0
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        raw = json.loads(text)
        return parse_llm_json(raw, provider="gemini", model_name=self._model)
