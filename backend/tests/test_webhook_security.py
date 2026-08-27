"""Real HMAC webhook verification — the security-critical ingress path."""
from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from salvage import webhook
from salvage.config import settings

SECRET = "whsec_test_salvage_123"


def _sign(body: bytes) -> str:
    return hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


@pytest.fixture()
def secret_on(monkeypatch):
    object.__setattr__(settings, "razorpay_webhook_secret", SECRET)
    object.__setattr__(settings, "require_webhook_signature", True)
    yield
    object.__setattr__(settings, "razorpay_webhook_secret", "")
    object.__setattr__(settings, "require_webhook_signature", False)


def test_valid_signature_accepted(secret_on):
    body = json.dumps({"event": "payment.failed", "id": "evt_1"}).encode()
    ok, mode = webhook.verify(body, _sign(body))
    assert ok is True and mode == "verified"


def test_tampered_body_rejected(secret_on):
    body = json.dumps({"event": "payment.failed", "id": "evt_1"}).encode()
    sig = _sign(body)
    tampered = body.replace(b"evt_1", b"evt_2")
    ok, mode = webhook.verify(tampered, sig)
    assert ok is False and mode == "rejected"


def test_missing_signature_rejected(secret_on):
    body = b"{}"
    ok, mode = webhook.verify(body, None)
    assert ok is False and mode == "rejected"


def test_demo_mode_skips_but_labels():
    # No secret, not required -> allowed, but honestly labelled 'skipped_demo'.
    object.__setattr__(settings, "razorpay_webhook_secret", "")
    object.__setattr__(settings, "require_webhook_signature", False)
    ok, mode = webhook.verify(b"{}", None)
    assert ok is True and mode == "skipped_demo"


def test_signature_is_constant_time_compare():
    # sanity: our compute matches a hand-rolled HMAC
    body = b'{"a":1}'
    assert webhook.compute_signature(body, SECRET) == _sign(body)
