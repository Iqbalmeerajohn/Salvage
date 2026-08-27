"""Synthetic merchant dataset generator.

Deterministic (seeded) so every demo run is byte-identical. Produces a small but
realistic e-commerce merchant: customers across segments, products, orders,
and payments where a believable share fail for believable reasons. The failed
payments are what SALVAGE acts on.

EVERYTHING here is labelled synthetic. No real person, card, or merchant exists
in this data. See data/README.md, emitted alongside the files.

Money is integer paise throughout. Stdlib only — no third-party deps.
"""
from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .enums import RootCause

SEED = 20260905  # the submission date — deterministic, memorable
NOW = datetime(2026, 8, 27, 12, 0, 0, tzinfo=timezone.utc)

SEGMENTS = ("new", "regular", "vip", "at_risk")
METHODS = ("upi", "card", "netbanking")
# UPI dominates failures in India — reflect that in the mix.
METHOD_WEIGHTS = (0.58, 0.30, 0.12)

FAILURE_REASONS = (
    RootCause.INSUFFICIENT_FUNDS,
    RootCause.OTP_DROP,
    RootCause.BANK_DOWNTIME,
    RootCause.RISK_BLOCK,
    RootCause.EXPIRED_INSTRUMENT,
    RootCause.UNKNOWN,
)
FAILURE_WEIGHTS = (0.34, 0.24, 0.14, 0.08, 0.12, 0.08)

PRODUCTS = [
    ("Cold brew subscription", 34_000, "food"),
    ("Yoga mat pro", 189_900, "fitness"),
    ("Running shoes", 459_000, "fitness"),
    ("Skincare set", 129_900, "beauty"),
    ("Wireless earbuds", 249_900, "electronics"),
    ("Standing desk", 1_299_000, "home"),
    ("Protein 1kg", 219_900, "fitness"),
    ("Ceramic dinner set", 349_900, "home"),
]

SYNTHETIC = True  # every emitted record carries this flag


@dataclass
class Customer:
    id: str
    name: str
    segment: str
    lifetime_value_paise: int
    orders_count: int
    days_since_last_order: int
    incentives_last_30d: int
    is_churn_risk: bool
    is_flagged_abuse: bool
    synthetic: bool = True


@dataclass
class Product:
    id: str
    name: str
    price_paise: int
    category: str
    synthetic: bool = True


@dataclass
class Payment:
    id: str
    order_id: str
    customer_id: str
    amount_paise: int
    method: str
    status: str                 # "captured" | "failed"
    failure_reason: str | None  # a RootCause value, or None if captured
    created_at: str             # ISO8601
    synthetic: bool = True


@dataclass
class Dataset:
    customers: list[Customer] = field(default_factory=list)
    products: list[Product] = field(default_factory=list)
    payments: list[Payment] = field(default_factory=list)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def generate(n_customers: int = 60, seed: int = SEED) -> Dataset:
    rng = random.Random(seed)
    ds = Dataset()

    ds.products = [
        Product(id=f"prod_{i:03d}", name=name, price_paise=price, category=cat)
        for i, (name, price, cat) in enumerate(PRODUCTS)
    ]

    for i in range(n_customers):
        segment = rng.choices(SEGMENTS, weights=(0.25, 0.4, 0.15, 0.2))[0]
        orders_count = {
            "new": rng.randint(0, 1),
            "regular": rng.randint(2, 12),
            "vip": rng.randint(13, 60),
            "at_risk": rng.randint(3, 20),
        }[segment]
        ltv = orders_count * rng.randint(80_000, 400_000)
        ds.customers.append(
            Customer(
                id=f"cust_{i:03d}",
                name=f"Synthetic Customer {i:03d}",
                segment=segment,
                lifetime_value_paise=ltv,
                orders_count=orders_count,
                days_since_last_order=rng.randint(0, 120),
                incentives_last_30d=rng.choices((0, 1, 2, 3), weights=(0.6, 0.25, 0.1, 0.05))[0],
                is_churn_risk=(segment == "at_risk") or (rng.random() < 0.1),
                is_flagged_abuse=(rng.random() < 0.04),
            )
        )

    # Generate payments: each customer has a handful; ~22% fail.
    pay_i = 0
    for cust in ds.customers:
        n_payments = max(1, cust.orders_count // 2 + rng.randint(0, 2))
        for _ in range(n_payments):
            product = rng.choice(ds.products)
            amount = product.price_paise
            method = rng.choices(METHODS, weights=METHOD_WEIGHTS)[0]
            failed = rng.random() < 0.22
            reason = rng.choices(FAILURE_REASONS, weights=FAILURE_WEIGHTS)[0] if failed else None
            created = NOW - timedelta(
                days=rng.randint(0, 29), hours=rng.randint(0, 23), minutes=rng.randint(0, 59)
            )
            ds.payments.append(
                Payment(
                    id=f"pay_{pay_i:04d}",
                    order_id=f"order_{pay_i:04d}",
                    customer_id=cust.id,
                    amount_paise=amount,
                    method=method,
                    status="failed" if failed else "captured",
                    failure_reason=reason.value if reason else None,
                    created_at=_iso(created),
                )
            )
            pay_i += 1

    _plant_hero_cases(ds)
    return ds


def _plant_hero_cases(ds: Dataset) -> None:
    """Fixed, known cases the demo narrates. Deterministic ids so the video and
    the dashboard always show the same story."""
    # 1) The refusal case: churn-risk, 2 incentives in 30d, hard decline.
    hero_cust = Customer(
        id="cust_hero_refuse",
        name="Synthetic Customer HERO-REFUSE",
        segment="at_risk",
        lifetime_value_paise=210_000,
        orders_count=4,
        days_since_last_order=41,
        incentives_last_30d=2,
        is_churn_risk=True,
        is_flagged_abuse=False,
    )
    # 2) The healthy-customer case: gets a capped incentive, needs approval.
    hero_good = Customer(
        id="cust_hero_recover",
        name="Synthetic Customer HERO-RECOVER",
        segment="vip",
        lifetime_value_paise=1_500_000,
        orders_count=18,
        days_since_last_order=9,
        incentives_last_30d=0,
        is_churn_risk=False,
        is_flagged_abuse=False,
    )
    ds.customers.extend([hero_cust, hero_good])
    ds.payments.append(
        Payment(
            id="pay_hero_refuse",
            order_id="order_hero_refuse",
            customer_id="cust_hero_refuse",
            amount_paise=340_000,
            method="upi",
            status="failed",
            failure_reason=RootCause.INSUFFICIENT_FUNDS.value,
            created_at=_iso(NOW - timedelta(hours=2)),
        )
    )
    ds.payments.append(
        Payment(
            id="pay_hero_recover",
            order_id="order_hero_recover",
            customer_id="cust_hero_recover",
            amount_paise=340_000,
            method="upi",
            status="failed",
            failure_reason=RootCause.OTP_DROP.value,
            created_at=_iso(NOW - timedelta(hours=1)),
        )
    )
    ds.payments.append(
        Payment(
            id="pay_hero_bankdown",
            order_id="order_hero_bankdown",
            customer_id="cust_hero_recover",
            amount_paise=459_000,
            method="netbanking",
            status="failed",
            failure_reason=RootCause.BANK_DOWNTIME.value,
            created_at=_iso(NOW - timedelta(minutes=30)),
        )
    )


def write(ds: Dataset, out_dir: Path) -> dict[str, int]:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "customers.json").write_text(
        json.dumps([asdict(c) for c in ds.customers], indent=2), encoding="utf-8"
    )
    (out_dir / "products.json").write_text(
        json.dumps([asdict(p) for p in ds.products], indent=2), encoding="utf-8"
    )
    (out_dir / "payments.json").write_text(
        json.dumps([asdict(p) for p in ds.payments], indent=2), encoding="utf-8"
    )
    failed = [p for p in ds.payments if p.status == "failed"]
    (out_dir / "README.md").write_text(
        "# SYNTHETIC DATA — not real\n\n"
        "Every record in this directory is generated by `salvage/synth.py` with a\n"
        f"fixed seed ({SEED}). No real person, card, bank, or merchant is represented.\n"
        "Amounts are integer paise. This exists so SALVAGE can be demonstrated without\n"
        "a live merchant.\n\n"
        f"- customers: {len(ds.customers)}\n"
        f"- products: {len(ds.products)}\n"
        f"- payments: {len(ds.payments)} ({len(failed)} failed)\n\n"
        "Hero cases (deterministic ids used by the demo):\n"
        "- `pay_hero_refuse` — churn-risk customer, 2 incentives in 30d → SALVAGE refuses.\n"
        "- `pay_hero_recover` — healthy VIP, OTP drop → capped incentive, needs approval.\n"
        "- `pay_hero_bankdown` — bank downtime → forced switch-rail, no money.\n",
        encoding="utf-8",
    )
    return {
        "customers": len(ds.customers),
        "products": len(ds.products),
        "payments": len(ds.payments),
        "failed": len(failed),
    }
