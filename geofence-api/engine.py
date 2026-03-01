"""
Geofence + Decision Engine

Two responsibilities:
  1. Geofence math — Haversine distance, active-hours check, find which
     geofence (if any) a coordinate falls inside.
  2. Decision layer — classify customer, select a merchant-approved discount
     tier, apply loyalty token bonus, build a Stripe offer.

Loyalty Token System
--------------------
Customers earn tokens on every qualifying checkin (one that triggers a geofence
and results in an offer). Tokens decay when the customer goes inactive.

Token → Tier mapping:
    0-9    none      no bonus
    10-24  bronze    +2 percentage points
    25-49  silver    +5 percentage points
    50-99  gold      +10 percentage points
    100+   platinum  +15 percentage points

Token accrual per visit:
    new_customer      +3  (welcome bonus)
    regular           +2
    frequent_visitor  +4  (reward the habit)
    lapsed_customer   +1  (they came back, but no windfall)

Decay (applied on each checkin, before accrual):
    30-59 days inactive ->  -5 tokens
    60-89 days inactive -> -15 tokens
    90+   days inactive ->  reset to 0
"""

import math
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Any, Dict, Optional, Tuple
from uuid import uuid4

import models
from sqlalchemy.orm import Session


# ── Geofence helpers ──────────────────────────────────────────────────────────

def haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Return distance in metres between two WGS-84 coordinates."""
    R = 6_371_000  # Earth radius in metres
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def is_within_active_hours(geofence: models.Geofence) -> bool:
    """Return True if the current local time is inside the geofence's active window.
    Active hours are interpreted as America/Chicago local time (where merchants are located).
    """
    local_tz = ZoneInfo("America/Chicago")
    current = datetime.now(local_tz).strftime("%H:%M")
    start, end = geofence.active_hours_start, geofence.active_hours_end
    # Handle overnight windows, e.g. "18:00" → "02:00"
    if start <= end:
        return start <= current <= end
    return current >= start or current <= end


def find_triggered_geofence(
    lat: float, lng: float, geofences: list
) -> Optional[models.Geofence]:
    """Return the closest active geofence that contains (lat, lng), or None."""
    best: Optional[models.Geofence] = None
    best_dist = float("inf")

    for geo in geofences:
        if not geo.is_active:
            continue
        dist = haversine_distance(lat, lng, geo.lat, geo.lng)
        if dist <= geo.radius_meters and dist < best_dist:
            best = geo
            best_dist = dist

    return best



# ── Loyalty token system ──────────────────────────────────────────────────────

# (min_tokens, tier_name, discount_bonus_pp) — ordered highest first
LOYALTY_TIERS = [
    (100, "platinum", 15),
    (50,  "gold",     10),
    (25,  "silver",    5),
    (10,  "bronze",    2),
    (0,   "none",      0),
]

TOKEN_ACCRUAL: Dict[str, int] = {
    "new_customer":     3,
    "frequent_visitor": 4,
    "regular":          2,
    "lapsed_customer":  1,
}

TIER_EMOJI: Dict[str, str] = {
    "platinum": "💎 Platinum",
    "gold":     "🥇 Gold",
    "silver":   "🥈 Silver",
    "bronze":   "🥉 Bronze",
    "none":     "",
}


def resolve_loyalty_tier(tokens: int) -> Tuple[str, int]:
    """Return (tier_name, discount_bonus_pp) for a given token count."""
    for min_t, name, bonus in LOYALTY_TIERS:
        if tokens >= min_t:
            return name, bonus
    return "none", 0


def apply_token_decay(customer: models.Customer, days_since: int) -> int:
    """Decay tokens based on inactivity. Modifies customer in-place."""
    tokens = customer.loyalty_tokens
    if days_since >= 90:
        tokens = 0
    elif days_since >= 60:
        tokens = max(0, tokens - 15)
    elif days_since >= 30:
        tokens = max(0, tokens - 5)
    customer.loyalty_tokens = tokens
    return tokens


def accrue_tokens(customer: models.Customer, tier_type: str) -> int:
    """Add visit tokens. Modifies customer in-place."""
    customer.loyalty_tokens += TOKEN_ACCRUAL.get(tier_type, 2)
    return customer.loyalty_tokens


def update_loyalty_tier(customer: models.Customer) -> Tuple[str, int]:
    """Recalculate and persist tier label. Returns (tier_name, bonus_pp)."""
    tier, bonus = resolve_loyalty_tier(customer.loyalty_tokens)
    customer.loyalty_tier = tier
    return tier, bonus


def process_loyalty_tokens(
    customer: models.Customer,
    tier_type: str,
    days_since: int,
) -> Tuple[str, int]:
    """
    Full token lifecycle for one checkin: decay -> accrue -> recalculate tier.
    Returns (new_tier_name, new_token_count). Call before db.commit().
    """
    apply_token_decay(customer, days_since)
    accrue_tokens(customer, tier_type)
    tier, _ = update_loyalty_tier(customer)
    return tier, customer.loyalty_tokens


# ── Customer context ──────────────────────────────────────────────────────────

def build_customer_context(
    customer: Optional[models.Customer],
    db: Session,
    merchant_id: str,
    external_user_id: str,
) -> Dict[str, Any]:
    """Build a context dict used by the decision layer."""
    if customer is None:
        return {
            "total_visits": 0,
            "visits_last_7_days": 0,
            "days_since_last_visit": 999,
            "avg_spend": 0.0,
            "current_hour": datetime.now(timezone.utc).hour,
            "loyalty_tokens": 0,
            "loyalty_tier": "none",
            "loyalty_bonus_pp": 0,
        }

    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    visits_7d = (
        db.query(models.CheckinEvent)
        .filter(
            models.CheckinEvent.merchant_id == merchant_id,
            models.CheckinEvent.external_user_id == external_user_id,
            models.CheckinEvent.triggered == True,
            models.CheckinEvent.timestamp >= seven_days_ago,
        )
        .count()
    )

    days_since = 999
    if customer.last_seen:
        last = customer.last_seen
        # Make last_seen offset-aware if stored as naive UTC
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        days_since = (datetime.now(timezone.utc) - last).days

    _, bonus_pp = resolve_loyalty_tier(customer.loyalty_tokens)

    return {
        "total_visits": customer.total_visits,
        "visits_last_7_days": visits_7d,
        "days_since_last_visit": days_since,
        "avg_spend": customer.avg_spend,
        "current_hour": datetime.now(timezone.utc).hour,
        "loyalty_tokens": customer.loyalty_tokens,
        "loyalty_tier": customer.loyalty_tier,
        "loyalty_bonus_pp": bonus_pp,
    }


# ── Decision engine ───────────────────────────────────────────────────────────

def classify_customer(context: Dict[str, Any]) -> str:
    """Rule-based classifier — swap out for an LLM call when ready."""
    total = context["total_visits"]
    days_since = context["days_since_last_visit"]
    visits_7d = context["visits_last_7_days"]

    if total == 0:
        return "new_customer"
    if days_since >= 30:
        return "lapsed_customer"
    if visits_7d >= 3:
        return "frequent_visitor"
    return "regular"


_EXPLANATIONS: Dict[str, str] = {
    "new_customer": "Welcome! Enjoy a discount on your first visit.",
    "lapsed_customer": "We've missed you! Here's something to welcome you back.",
    "frequent_visitor": "Thanks for being such a regular — this one's on us.",
    "regular": "Thanks for stopping by! Here's a little something for you.",
}


def select_discount_tier(
    geofence: models.Geofence,
    tier_type: str,
    context: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """
    Pick a base discount from the merchant's approved tiers, then apply the
    loyalty token bonus on top. Hard-caps at geofence.max_discount.
    """
    tiers: Dict[str, int] = {t.tier_type: t.percent for t in geofence.discount_tiers}
    if not tiers:
        return None

    if tier_type in tiers:
        chosen_type = tier_type
        base_percent = tiers[tier_type]
    else:
        # Graceful fallback: use cheapest available tier
        chosen_type = min(tiers, key=lambda k: tiers[k])
        base_percent = tiers[chosen_type]

    # Apply loyalty bonus on top of base, capped at merchant max
    loyalty_tier = context.get("loyalty_tier", "none")
    bonus_pp     = context.get("loyalty_bonus_pp", 0)
    final_percent = min(base_percent + bonus_pp, geofence.max_discount)

    explanation = _EXPLANATIONS.get(chosen_type, "Special offer just for you!")
    if chosen_type == "lapsed_customer" and context["days_since_last_visit"] < 999:
        explanation = (
            f"We've missed you! It's been {context['days_since_last_visit']} days "
            "since your last visit."
        )
    if chosen_type == "frequent_visitor":
        explanation = (
            f"Thanks for being a regular! You've visited "
            f"{context['visits_last_7_days']} times this week."
        )

    # Append loyalty bonus callout when applicable
    if loyalty_tier != "none" and bonus_pp > 0:
        label = TIER_EMOJI.get(loyalty_tier, loyalty_tier.capitalize())
        explanation += (
            f" {label} loyalty bonus applied: +{bonus_pp}% "
            f"(base {base_percent}% -> {final_percent}% total)."
        )

    return {
        "tier_type":       chosen_type,
        "percent":         final_percent,
        "base_percent":    base_percent,
        "loyalty_tier":    loyalty_tier,
        "loyalty_bonus_pp": bonus_pp,
        "loyalty_tokens":  context.get("loyalty_tokens", 0),
        "explanation":     explanation,
    }


# ── Stripe integration ────────────────────────────────────────────────────────

def create_stripe_offer(
    merchant: models.Merchant,
    discount_percent: int,
    price_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a Stripe Coupon + PaymentLink on the main Stripe account.
    stripe_account_id is optional — only used when Stripe Connect is configured.
    Falls back to a local mock checkout page when credentials are missing.
    """
    stripe_key = os.getenv("STRIPE_SECRET_KEY")
    effective_price_id = (
        price_id
        or (merchant.stripe_price_id if hasattr(merchant, "stripe_price_id") else None)
        or os.getenv("DEFAULT_PRICE_ID", "")
    )

    # Only treat a price_id as real if it actually looks like one
    price_is_real = (
        bool(effective_price_id)
        and effective_price_id.startswith("price_")
        and "..." not in effective_price_id
        and len(effective_price_id) > 10
    )

    if not stripe_key or not price_is_real:
        mock_id = uuid4().hex[:12]
        base = os.getenv("API_BASE_URL", "http://localhost:8000")
        return {
            "coupon_id": f"mock_coupon_{mock_id}",
            "payment_link": f"{base}/demo/checkout/{mock_id}",
            "mock": True,
        }

    import stripe

    stripe.api_key = stripe_key

    # stripe_account is only passed when the merchant has a connected account (Stripe Connect).
    # For the demo, merchants have no connected account, so we bill via the main account.
    connected: Optional[str] = merchant.stripe_account_id or None
    base = os.getenv("API_BASE_URL", "http://localhost:8001")

    try:
        coupon_kwargs: Dict[str, Any] = {
            "percent_off": discount_percent,
            "duration": "once",
            "max_redemptions": 1,
        }
        if connected:
            coupon_kwargs["stripe_account"] = connected

        coupon = stripe.Coupon.create(**coupon_kwargs)

        # checkout.Session is more reliable than PaymentLink for coupon discounts
        session_kwargs: Dict[str, Any] = {
            "payment_method_types": ["card"],
            "line_items": [{"price": effective_price_id, "quantity": 1}],
            "mode": "payment",
            "discounts": [{"coupon": coupon.id}],
            "success_url": f"{base}/?checkout=success",
            "cancel_url": f"{base}/?checkout=cancel",
        }
        if connected:
            session_kwargs["stripe_account"] = connected

        session = stripe.checkout.Session.create(**session_kwargs)
        return {"coupon_id": coupon.id, "payment_link": session.url, "mock": False}

    except Exception as exc:
        mock_id = uuid4().hex[:8]
        return {
            "coupon_id": f"err_coupon_{mock_id}",
            "payment_link": f"{base}/demo/checkout/{mock_id}",
            "mock": True,
            "error": str(exc),
        }