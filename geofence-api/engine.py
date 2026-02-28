"""
Geofence + Decision Engine

Two responsibilities:
  1. Geofence math — Haversine distance, active-hours check, find which
     geofence (if any) a coordinate falls inside.
  2. Decision layer — classify customer, select a merchant-approved discount
     tier, build a Stripe offer (or a mock when no Stripe creds are set).
"""

import math
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
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
    """Return True if the current UTC time is inside the geofence's active window."""
    current = datetime.now(timezone.utc).strftime("%H:%M")
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

    return {
        "total_visits": customer.total_visits,
        "visits_last_7_days": visits_7d,
        "days_since_last_visit": days_since,
        "avg_spend": customer.avg_spend,
        "current_hour": datetime.now(timezone.utc).hour,
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
    Pick a discount from the merchant's approved tiers.
    Falls back to the lowest tier if the classified type isn't configured.
    Hard-caps at geofence.max_discount.
    """
    tiers: Dict[str, int] = {t.tier_type: t.percent for t in geofence.discount_tiers}
    if not tiers:
        return None

    if tier_type in tiers:
        chosen_type = tier_type
        percent = tiers[tier_type]
    else:
        # Graceful fallback: use cheapest available tier
        chosen_type = min(tiers, key=lambda k: tiers[k])
        percent = tiers[chosen_type]

    percent = min(percent, geofence.max_discount)

    explanation = _EXPLANATIONS.get(chosen_type, "Special offer just for you!")
    # Enrich lapsed explanation with actual days
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

    return {"tier_type": chosen_type, "percent": percent, "explanation": explanation}


# ── Stripe integration ────────────────────────────────────────────────────────

def create_stripe_offer(
    merchant: models.Merchant,
    discount_percent: int,
    price_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a Stripe Coupon + PaymentLink inside the merchant's connected account.
    Falls back to a clearly-labelled mock when no Stripe credentials are configured.
    """
    stripe_key = os.getenv("STRIPE_SECRET_KEY")
    effective_price_id = price_id or os.getenv("DEFAULT_PRICE_ID", "")

    if not stripe_key or not merchant.stripe_account_id or not effective_price_id:
        mock_id = uuid4().hex[:12]
        return {
            "coupon_id": f"mock_coupon_{mock_id}",
            "payment_link": f"https://buy.stripe.com/mock_{mock_id}",
            "mock": True,
        }

    import stripe  # imported lazily so the app boots without the package if unused

    stripe.api_key = stripe_key
    try:
        coupon = stripe.Coupon.create(
            percent_off=discount_percent,
            duration="once",
            max_redemptions=1,
            stripe_account=merchant.stripe_account_id,
        )
        payment_link = stripe.PaymentLink.create(
            line_items=[{"price": effective_price_id, "quantity": 1}],
            discounts=[{"coupon": coupon.id}],
            stripe_account=merchant.stripe_account_id,
        )
        return {"coupon_id": coupon.id, "payment_link": payment_link.url, "mock": False}

    except Exception as exc:
        mock_id = uuid4().hex[:8]
        return {
            "coupon_id": f"err_coupon_{mock_id}",
            "payment_link": f"https://buy.stripe.com/mock_{mock_id}",
            "mock": True,
            "error": str(exc),
        }
