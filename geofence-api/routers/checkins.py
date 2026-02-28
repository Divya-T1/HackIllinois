from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
import engine as geo_engine
import models, schemas

router = APIRouter()

# How long to wait before re-offering the same user at the same merchant
OFFER_COOLDOWN_HOURS = 6


@router.post("/checkins", response_model=schemas.CheckinResponse)
def process_checkin(
    payload: schemas.CheckinRequest,
    merchant_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    Public endpoint — no API key required.
    Accepts merchant_id either in the request body or as a query param.
    This makes it easy to use from the demo frontend.
    """
    mid = payload.merchant_id or merchant_id
    if not mid:
        raise HTTPException(status_code=400, detail="merchant_id is required")

    merchant = db.query(models.Merchant).filter(models.Merchant.id == mid).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")

    # ── 1. Find which geofence (if any) the user is inside ───────────────────
    geofences = (
        db.query(models.Geofence)
        .filter(models.Geofence.merchant_id == mid, models.Geofence.is_active == True)
        .all()
    )
    triggered = geo_engine.find_triggered_geofence(payload.lat, payload.lng, geofences)

    # Log the raw checkin regardless of outcome
    checkin = models.CheckinEvent(
        merchant_id=mid,
        external_user_id=payload.user_id,
        lat=payload.lat,
        lng=payload.lng,
        geofence_id=triggered.id if triggered else None,
        triggered=triggered is not None,
    )
    db.add(checkin)

    if not triggered:
        db.commit()
        return schemas.CheckinResponse(
            enabled=False,
            message="Not within any active geofence",
        )

    # ── 2. Active-hours check ─────────────────────────────────────────────────
    if not geo_engine.is_within_active_hours(triggered):
        db.commit()
        return schemas.CheckinResponse(
            enabled=False,
            message=(
                f"Outside active hours "
                f"({triggered.active_hours_start}–{triggered.active_hours_end} UTC)"
            ),
        )

    # ── 3. Rate-limit: one offer per OFFER_COOLDOWN_HOURS per merchant ────────
    cooldown_cutoff = datetime.now(timezone.utc) - timedelta(hours=OFFER_COOLDOWN_HOURS)
    recent = (
        db.query(models.Offer)
        .filter(
            models.Offer.merchant_id == mid,
            models.Offer.external_user_id == payload.user_id,
            models.Offer.created_at >= cooldown_cutoff,
        )
        .first()
    )
    if recent:
        db.commit()
        return schemas.CheckinResponse(
            enabled=False,
            message=f"You already have an active offer. Check back in {OFFER_COOLDOWN_HOURS}h.",
        )

    # ── 4. Get or create customer record ──────────────────────────────────────
    customer = (
        db.query(models.Customer)
        .filter(
            models.Customer.merchant_id == mid,
            models.Customer.external_user_id == payload.user_id,
        )
        .first()
    )
    if not customer:
        customer = models.Customer(merchant_id=mid, external_user_id=payload.user_id)
        db.add(customer)
        db.flush()

    # ── 5. Decision engine ────────────────────────────────────────────────────
    context = geo_engine.build_customer_context(customer, db, mid, payload.user_id)
    tier_type = geo_engine.classify_customer(context)
    decision = geo_engine.select_discount_tier(triggered, tier_type, context)

    if not decision:
        db.commit()
        return schemas.CheckinResponse(
            enabled=False,
            message="No eligible discount tier configured for this geofence",
        )

    # ── 6. Create Stripe coupon + payment link (or mock) ──────────────────────
    stripe_result = geo_engine.create_stripe_offer(merchant, decision["percent"])

    # ── 7. Persist offer ──────────────────────────────────────────────────────
    offer = models.Offer(
        merchant_id=mid,
        geofence_id=triggered.id,
        external_user_id=payload.user_id,
        discount_percent=decision["percent"],
        reason_code=decision["tier_type"],
        reason_explanation=decision["explanation"],
        stripe_coupon_id=stripe_result["coupon_id"],
        stripe_payment_link=stripe_result["payment_link"],
        status="pending",
    )
    db.add(offer)

    customer.last_seen = datetime.now(timezone.utc)
    customer.total_visits += 1

    db.commit()
    db.refresh(offer)

    return schemas.CheckinResponse(
        offer_id=offer.id,
        enabled=True,
        discount_percent=offer.discount_percent,
        personalization=schemas.OfferPersonalization(
            reason_code=offer.reason_code,
            explanation=offer.reason_explanation,
        ),
        stripe_payment_link=offer.stripe_payment_link,
        geofence_name=triggered.name,
        message="Offer generated successfully",
    )


@router.get("/offers/{offer_id}")
def get_offer(offer_id: str, db: Session = Depends(get_db)):
    offer = db.query(models.Offer).filter(models.Offer.id == offer_id).first()
    if not offer:
        raise HTTPException(status_code=404, detail="Offer not found")
    return {
        "offer_id": offer.id,
        "status": offer.status,
        "discount_percent": offer.discount_percent,
        "reason_code": offer.reason_code,
        "stripe_payment_link": offer.stripe_payment_link,
        "created_at": offer.created_at,
        "redeemed_at": offer.redeemed_at,
    }
