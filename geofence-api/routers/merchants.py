from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List

from database import get_db
from engine import haversine_distance
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


# NOTE: /nearby must be registered BEFORE /{merchant_id} so FastAPI routes it correctly
@router.get("/nearby", response_model=List[schemas.MerchantResponse])
def nearby_merchants(
    lat: float = Query(...),
    lng: float = Query(...),
    radius_meters: float = Query(default=1000),
    db: Session = Depends(get_db),
):
    """Return merchants that have at least one active geofence within radius_meters of (lat, lng)."""
    all_merchants = db.query(models.Merchant).all()
    result = []
    seen: set = set()

    for merchant in all_merchants:
        geofences = (
            db.query(models.Geofence)
            .filter(
                models.Geofence.merchant_id == merchant.id,
                models.Geofence.is_active == True,
            )
            .all()
        )
        for geo in geofences:
            dist = haversine_distance(lat, lng, geo.lat, geo.lng)
            # merchant is "nearby" if user's radius circle overlaps the geofence circle
            if dist <= radius_meters + geo.radius_meters and merchant.id not in seen:
                result.append(merchant)
                seen.add(merchant.id)
                break

    return result


@router.get("/{merchant_id}", response_model=schemas.MerchantResponse)
def get_merchant(merchant_id: str, db: Session = Depends(get_db)):
    merchant = db.query(models.Merchant).filter(models.Merchant.id == merchant_id).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")
    return merchant
