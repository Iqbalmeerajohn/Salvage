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


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    # Database (SQLite file; Postgres via DATABASE_URL/POSTGRES_URL* in the cloud).
    # On Vercel the deployment filesystem is read-only apart from /tmp, so the
    # SQLite fallback must live there or every DB-backed route 500s. This is only
    # a fallback: when a Postgres URL is configured, db.py uses that instead.
    db_path: str = os.getenv(
        "SALVAGE_DB",
        "/tmp/salvage.db"
        if os.getenv("VERCEL")
        else str(Path(__file__).resolve().parents[2] / "data" / "salvage.db"),
    )

    # LLM providers. Empty key => that provider is skipped, chain falls to mock.
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
    local_llm_url: str = os.getenv("LOCAL_LLM_URL", "")  # e.g. http://localhost:11434
    local_llm_model: str = os.getenv("LOCAL_LLM_MODEL", "llama3.2")

    # Razorpay test mode. Empty => mock gateway (deterministic fake links).
    razorpay_key_id: str = os.getenv("RAZORPAY_KEY_ID", "")
    razorpay_key_secret: str = os.getenv("RAZORPAY_KEY_SECRET", "")
    razorpay_webhook_secret: str = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")

    # Behaviour flags.
    require_webhook_signature: bool = _bool("REQUIRE_WEBHOOK_SIGNATURE", False)

    # Optional cap on how many real Payment Links may be created against the
    # Razorpay TEST account (test mode has a low quota). Deliberately NOT a
    # constant: set RAZORPAY_MAX_TEST_LINKS in the environment. 0 = no cap.
    # Only enforced when the real Razorpay gateway is active; the mock gateway
    # is unlimited because it creates nothing upstream.
    razorpay_max_test_links: int = _int("RAZORPAY_MAX_TEST_LINKS", 0)

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
