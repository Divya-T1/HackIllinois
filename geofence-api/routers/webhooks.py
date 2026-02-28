import json
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from database import get_db
import models

router = APIRouter()


@router.post("/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(default=None, alias="stripe-signature"),
    db: Session = Depends(get_db),
):
    """
    Receives Stripe webhook events.
    On checkout.session.completed → marks the matching offer as redeemed.
    """
    payload = await request.body()
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

    if webhook_secret and stripe_signature:
        import stripe

        try:
            event = stripe.Webhook.construct_event(payload, stripe_signature, webhook_secret)
        except stripe.error.SignatureVerificationError:
            raise HTTPException(status_code=400, detail="Invalid Stripe signature")
    else:
        # Dev / demo mode — no signature verification
        event = json.loads(payload)

    event_type = event["type"] if isinstance(event, dict) else event.type

    if event_type == "checkout.session.completed":
        session_obj = (
            event["data"]["object"] if isinstance(event, dict) else event.data.object
        )

        # Resolve offer via coupon id embedded in the session discount breakdown
        coupon_id: str | None = None
        try:
            discounts = session_obj["total_details"]["breakdown"]["discounts"]
            if discounts:
                coupon_id = discounts[0]["discount"]["coupon"]["id"]
        except (KeyError, TypeError, IndexError):
            pass

        if coupon_id:
            offer = (
                db.query(models.Offer)
                .filter(models.Offer.stripe_coupon_id == coupon_id)
                .first()
            )
            if offer and offer.status == "pending":
                offer.status = "redeemed"
                offer.redeemed_at = datetime.now(timezone.utc)
                db.commit()

    return {"received": True}
