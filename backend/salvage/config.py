"""Runtime configuration. Safe defaults mean the whole system runs offline in
demo mode with zero accounts and zero secrets. Adding env vars upgrades it to
live Gemini / live Razorpay test-mode without changing any code.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except Exception:
    pass  # dotenv is optional; env vars still work without it


def _bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    # Database (SQLite file; ports to Postgres in production).
    db_path: str = os.getenv(
        "SALVAGE_DB", str(Path(__file__).resolve().parents[2] / "data" / "salvage.db")
    )

    # LLM providers. Empty key => that provider is skipped, chain falls to mock.
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    local_llm_url: str = os.getenv("LOCAL_LLM_URL", "")  # e.g. http://localhost:11434
    local_llm_model: str = os.getenv("LOCAL_LLM_MODEL", "llama3.2")

    # Razorpay test mode. Empty => mock gateway (deterministic fake links).
    razorpay_key_id: str = os.getenv("RAZORPAY_KEY_ID", "")
    razorpay_key_secret: str = os.getenv("RAZORPAY_KEY_SECRET", "")
    razorpay_webhook_secret: str = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")

    # Behaviour flags.
    require_webhook_signature: bool = _bool("REQUIRE_WEBHOOK_SIGNATURE", False)

    @property
    def use_real_gateway(self) -> bool:
        return bool(self.razorpay_key_id and self.razorpay_key_secret)

    @property
    def gemini_enabled(self) -> bool:
        return bool(self.gemini_api_key)

    @property
    def local_enabled(self) -> bool:
        return bool(self.local_llm_url)


settings = Settings()
