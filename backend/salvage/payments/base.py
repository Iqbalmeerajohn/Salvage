"""Gateway interface + result type.

`create_recovery_link` is the only money-touching action in the system. It takes
an idempotency_key so that calling it twice with the same key yields the same
link — the property the outbox relies on for exactly-once execution.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class LinkResult:
    provider: str        # "mock" | "razorpay"
    link_id: str
    short_url: str
    status: str          # "created"


class PaymentGateway(Protocol):
    name: str

    def create_recovery_link(
        self, idempotency_key: str, amount_paise: int, description: str, customer_ref: str
    ) -> LinkResult: ...
