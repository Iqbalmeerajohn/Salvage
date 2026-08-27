"""Shared fixtures: a fresh temp SQLite DB seeded with the synthetic dataset,
plus an API client bound to an isolated database file per test."""
from __future__ import annotations

import pytest

from salvage.config import settings
from salvage.db import connect, init_db
from salvage.seed import DATA_DIR, load


@pytest.fixture(autouse=True)
def _force_offline_llm():
    """Tests are hermetic: force the deterministic mock LLM so no test depends on
    a network call or a live API key (a real GEMINI_API_KEY may be set in .env)."""
    prev_g = settings.gemini_api_key
    prev_l = settings.local_llm_url
    object.__setattr__(settings, "gemini_api_key", "")
    object.__setattr__(settings, "local_llm_url", "")
    yield
    object.__setattr__(settings, "gemini_api_key", prev_g)
    object.__setattr__(settings, "local_llm_url", prev_l)


@pytest.fixture()
def conn(tmp_path):
    db = str(tmp_path / "test.db")
    init_db(db)
    c = connect(db)
    if (DATA_DIR / "customers.json").exists():
        load(c)
    yield c
    c.close()


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """A TestClient whose backend points at an isolated temp DB."""
    from fastapi.testclient import TestClient

    import salvage.app as appmod

    db = str(tmp_path / "api.db")
    # settings is a frozen dataclass singleton; override the db path in place.
    object.__setattr__(settings, "db_path", db)
    monkeypatch.setattr(appmod, "_ready", False)
    init_db(db)
    c = connect(db)
    if (DATA_DIR / "customers.json").exists():
        load(c)
    c.close()
    return TestClient(appmod.app)
