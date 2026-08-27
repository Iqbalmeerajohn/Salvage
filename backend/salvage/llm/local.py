"""Optional local-model provider (e.g. Ollama). Only active if LOCAL_LLM_URL is
set. Kept thin: it's the middle fallback between Gemini and the mock, useful if
you want zero external calls but still a real model. Skipped entirely otherwise.
"""
from __future__ import annotations

import json

import httpx

from .base import Diagnosis, parse_llm_json
from ..config import settings
from ..enums import Play, RootCause

_PROMPT = (
    "Classify this failed payment and propose ONE recovery play. Output strict "
    "JSON with keys root_cause, proposed_play, proposed_incentive_pct, rationale.\n"
    f"root_cause in {[c.value for c in RootCause]}\n"
    f"proposed_play in {[p.value for p in Play]}\n"
    "Features: {features}\n"
)


class LocalProvider:
    name = "local"

    def __init__(self) -> None:
        self._url = settings.local_llm_url.rstrip("/")
        self._model = settings.local_llm_model

    def available(self) -> bool:
        return bool(self._url)

    def diagnose(self, features: dict) -> Diagnosis:
        # Ollama-compatible /api/generate with JSON format.
        resp = httpx.post(
            f"{self._url}/api/generate",
            json={
                "model": self._model,
                "prompt": _PROMPT.format(features=json.dumps(features)),
                "format": "json",
                "stream": False,
                "options": {"temperature": 0.2},
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        raw = json.loads(resp.json()["response"])
        return parse_llm_json(raw, provider="local", model_name=self._model)
