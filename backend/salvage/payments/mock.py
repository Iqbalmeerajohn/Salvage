"""Deterministic mock gateway for demo mode.

The link id is derived purely from the idempotency key, so re-executing the same
recovery — even after a crash and worker restart — produces the byte-identical
link id. Combined with the UNIQUE constraint on executions.idempotency_key, this
gives a provable exactly-once guarantee with no external service involved.
"""
from __future__ import annotations

import hashlib

from .base import LinkResult


class MockGateway:
    name = "mock"

    def create_recovery_link(
        self, idempotency_key: str, amount_paise: int, description: str, customer_ref: str
    ) -> LinkResult:
        h = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()[:16]
        link_id = f"plink_mock_{h}"
        return LinkResult(
            provider="mock",
            link_id=link_id,
            short_url=f"https://demo.salvage.local/pay/{link_id}",
            status="created",
        )
