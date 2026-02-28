from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from database import get_db
import models, schemas

router = APIRouter()


@router.get("/{merchant_id}/analytics", response_model=schemas.AnalyticsResponse)
def get_analytics(merchant_id: str, db: Session = Depends(get_db)):
    if not db.query(models.Merchant).filter(models.Merchant.id == merchant_id).first():
        raise HTTPException(status_code=404, detail="Merchant not found")

    total = (
        db.query(func.count(models.Offer.id))
        .filter(models.Offer.merchant_id == merchant_id)
        .scalar()
        or 0
    )
    redeemed = (
        db.query(func.count(models.Offer.id))
        .filter(
            models.Offer.merchant_id == merchant_id,
            models.Offer.status == "redeemed",
        )
        .scalar()
        or 0
    )

    redemption_rate = round((redeemed / total * 100) if total > 0 else 0.0, 2)

    return schemas.AnalyticsResponse(
        merchant_id=merchant_id,
        total_offers=total,
        redeemed_offers=redeemed,
        redemption_rate=redemption_rate,
        total_revenue=0.0,          # populated via Stripe webhook data in production
        conversion_percent=redemption_rate,
    )
