"""Hash-chained audit log.

Every meaningful step writes one append-only row. Each row's `this_hash` is
sha256(prev_hash + canonical_json(detail)). Because each hash covers the one
before it, you cannot alter, delete, or reorder a past row without breaking
every hash after it — which `verify_chain` detects. For a pre-IPO payments
company that must tell auditors "prove nothing was tampered with," this is the
whole point.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone

GENESIS = "0" * 64


def _canonical(detail: dict) -> str:
    # Sorted keys + no whitespace => stable bytes for hashing.
    return json.dumps(detail, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _hash(prev_hash: str, detail_json: str) -> str:
    return hashlib.sha256((prev_hash + detail_json).encode("utf-8")).hexdigest()


def append(conn: sqlite3.Connection, stage: str, detail: dict, recovery_id: str | None = None) -> str:
    row = conn.execute("SELECT this_hash FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
    prev_hash = row["this_hash"] if row else GENESIS
    detail_json = _canonical(detail)
    this_hash = _hash(prev_hash, detail_json)
    conn.execute(
        "INSERT INTO audit (recovery_id, stage, detail_json, prev_hash, this_hash, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (recovery_id, stage, detail_json, prev_hash, this_hash,
         datetime.now(timezone.utc).isoformat()),
    )
    return this_hash


def verify_chain(conn: sqlite3.Connection) -> tuple[bool, int | None]:
    """Recompute every hash. Returns (ok, first_broken_seq). ok=True means the
    entire chain is intact."""
    prev_hash = GENESIS
    for r in conn.execute("SELECT seq, detail_json, prev_hash, this_hash FROM audit ORDER BY seq"):
        if r["prev_hash"] != prev_hash:
            return False, r["seq"]
        if _hash(prev_hash, r["detail_json"]) != r["this_hash"]:
            return False, r["seq"]
        prev_hash = r["this_hash"]
    return True, None
