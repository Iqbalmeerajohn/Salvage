"""Webhook signature verification (Razorpay uses HMAC-SHA256).

Razorpay signs the raw request body with your webhook secret and sends the hex
digest in the `X-Razorpay-Signature` header. We recompute it and compare in
constant time. In demo mode (no secret, REQUIRE_WEBHOOK_SIGNATURE=false) we skip
verification so the loop runs offline — but we never *claim* a payload was
verified when it wasn't; the audit log records which path was taken.

Ref: https://razorpay.com/docs/webhooks/validate-test/
"""
from __future__ import annotations

import hashlib
import hmac

from .config import settings


def compute_signature(raw_body: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()


def verify(raw_body: bytes, signature: str | None) -> tuple[bool, str]:
    """Returns (ok, mode). mode is 'verified', 'skipped_demo', or 'rejected'."""
    if not settings.require_webhook_signature and not settings.razorpay_webhook_secret:
        return True, "skipped_demo"
    if not settings.razorpay_webhook_secret:
        return False, "rejected"  # required but no secret configured
    if not signature:
        return False, "rejected"
    expected = compute_signature(raw_body, settings.razorpay_webhook_secret)
    if hmac.compare_digest(expected, signature):
        return True, "verified"
    return False, "rejected"
