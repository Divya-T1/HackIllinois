from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from database import get_db
import models, schemas

router = APIRouter()


@router.post("/", response_model=schemas.PromotionResponse, status_code=201)
def create_promotion(payload: schemas.PromotionCreate, db: Session = Depends(get_db)):
    merchant = db.query(models.Merchant).filter(models.Merchant.id == payload.company_id).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")

    promo = models.MerchantPromotion(
        company_id=payload.company_id,
        description=payload.description,
        timeline=payload.timeline,
    )
    db.add(promo)
    db.commit()
    db.refresh(promo)
    return promo


@router.get("/", response_model=List[schemas.PromotionResponse])
def list_promotions(db: Session = Depends(get_db)):
    return db.query(models.MerchantPromotion).all()


@router.get("/{company_id}", response_model=List[schemas.PromotionResponse])
def get_promotions_for_merchant(company_id: str, db: Session = Depends(get_db)):
    return (
        db.query(models.MerchantPromotion)
        .filter(models.MerchantPromotion.company_id == company_id)
        .all()
    )
