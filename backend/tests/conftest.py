"""Shared fixtures: a fresh temp SQLite DB seeded with the synthetic dataset."""
from __future__ import annotations

from pathlib import Path

import pytest

from salvage.db import connect, init_db
from salvage.seed import DATA_DIR, load


@pytest.fixture()
def conn(tmp_path):
    db = str(tmp_path / "test.db")
    init_db(db)
    c = connect(db)
    if (DATA_DIR / "customers.json").exists():
        load(c)
    yield c
    c.close()
