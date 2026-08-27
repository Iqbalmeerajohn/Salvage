"""Selects the gateway based on config: real Razorpay if keys present, else mock."""
from __future__ import annotations

from ..config import settings
from .base import PaymentGateway
from .mock import MockGateway
from .razorpay import RazorpayGateway


def get_gateway() -> PaymentGateway:
    if settings.use_real_gateway:
        return RazorpayGateway()
    return MockGateway()
