"""Provider router: tries Gemini, then local, then the deterministic mock.

The mock always succeeds, so diagnosis never hard-fails. The returned Diagnosis
always carries the provider that ACTUALLY produced it, so a fallback is visible
in the UI and audit trail rather than silently masquerading as a live model.
"""
from __future__ import annotations

from ..config import settings
from .base import Diagnosis, LLMProvider
from .gemini import GeminiProvider
from .local import LocalProvider
from .mock import MockProvider


class Router:
    def __init__(self, providers: list[LLMProvider] | None = None) -> None:
        if providers is not None:
            self.providers = providers
        else:
            chain: list[LLMProvider] = []
            if settings.gemini_enabled:
                chain.append(GeminiProvider())
            if settings.local_enabled:
                chain.append(LocalProvider())
            chain.append(MockProvider())  # always last, always available
            self.providers = chain

    def diagnose(self, features: dict) -> tuple[Diagnosis, list[str]]:
        """Returns (diagnosis, notes). notes records any provider that was tried
        and failed, for transparency in the audit log."""
        notes: list[str] = []
        for p in self.providers:
            if not p.available():
                continue
            try:
                return p.diagnose(features), notes
            except Exception as exc:  # fall through to next provider
                notes.append(f"{p.name} failed: {type(exc).__name__}: {exc}")
        # MockProvider guarantees this is unreachable, but be explicit.
        raise RuntimeError("no LLM provider available")  # pragma: no cover
