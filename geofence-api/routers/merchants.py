from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from database import get_db
import models, schemas

router = APIRouter()


@router.post("/", response_model=schemas.MerchantResponse, status_code=201)
def create_merchant(payload: schemas.MerchantCreate, db: Session = Depends(get_db)):
    if db.query(models.Merchant).filter(models.Merchant.email == payload.email).first():
        raise HTTPException(status_code=409, detail="Email already registered")

    merchant = models.Merchant(name=payload.name, email=payload.email)
    db.add(merchant)
    db.commit()
    db.refresh(merchant)
    return merchant


@router.get("/", response_model=List[schemas.MerchantResponse])
def list_merchants(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    return db.query(models.Merchant).offset(skip).limit(limit).all()


@router.get("/{merchant_id}", response_model=schemas.MerchantResponse)
def get_merchant(merchant_id: str, db: Session = Depends(get_db)):
    merchant = db.query(models.Merchant).filter(models.Merchant.id == merchant_id).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")
    return merchant
