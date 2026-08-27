"""Real Razorpay test-mode gateway (Payment Links API).

Active only when RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET are set. Uses HTTP Basic
auth (key_id:key_secret) over the test-mode base URL. We do NOT rely on Razorpay
for idempotency — our outbox + executions.UNIQUE(idempotency_key) owns that. This
client just performs the single create call; the caller records the result under
the idempotency key exactly once.

Docs the user should confirm are current before live testing:
  - Payment Links: https://razorpay.com/docs/api/payments/payment-links/
  - Authentication: https://razorpay.com/docs/api/authentication/
"""
from __future__ import annotations

import httpx

from .base import LinkResult
from ..config import settings

_BASE = "https://api.razorpay.com/v1"


class RazorpayGateway:
    name = "razorpay"

    def __init__(self) -> None:
        self._auth = (settings.razorpay_key_id, settings.razorpay_key_secret)

    def create_recovery_link(
        self, idempotency_key: str, amount_paise: int, description: str, customer_ref: str
    ) -> LinkResult:
        payload = {
            "amount": amount_paise,
            "currency": "INR",
            "description": description[:2048],
            "reference_id": idempotency_key,  # our key; lets us reconcile later
            "notify": {"sms": False, "email": False},  # we control comms ourselves
            "reminder_enable": False,
            "notes": {"salvage_customer_ref": customer_ref, "salvage_idem": idempotency_key},
        }
        resp = httpx.post(
            f"{_BASE}/payment_links", auth=self._auth, json=payload, timeout=20.0
        )
        resp.raise_for_status()
        data = resp.json()
        return LinkResult(
            provider="razorpay",
            link_id=data["id"],
            short_url=data.get("short_url", ""),
            status=data.get("status", "created"),
        )
