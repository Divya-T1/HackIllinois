from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from database import get_db
from auth import get_merchant
import models, schemas

router = APIRouter()


@router.post(
    "/{merchant_id}/geofences",
    response_model=schemas.GeofenceResponse,
    status_code=201,
)
def create_geofence(
    merchant_id: str,
    payload: schemas.GeofenceCreate,
    db: Session = Depends(get_db),
    merchant: models.Merchant = Depends(get_merchant),
):
    if merchant.id != merchant_id:
        raise HTTPException(status_code=403, detail="Access denied")

    geofence = models.Geofence(
        merchant_id=merchant_id,
        name=payload.name,
        lat=payload.lat,
        lng=payload.lng,
        radius_meters=payload.radius_meters,
        max_discount=payload.max_discount,
        active_hours_start=payload.active_hours.start,
        active_hours_end=payload.active_hours.end,
    )
    db.add(geofence)
    db.flush()

    for tier in payload.discount_tiers:
        db.add(
            models.DiscountTier(
                geofence_id=geofence.id,
                tier_type=tier.type,
                percent=min(tier.percent, payload.max_discount),
            )
        )

    db.commit()
    db.refresh(geofence)
    return geofence


@router.get("/{merchant_id}/geofences", response_model=List[schemas.GeofenceResponse])
def list_geofences(merchant_id: str, db: Session = Depends(get_db)):
    return (
        db.query(models.Geofence)
        .filter(models.Geofence.merchant_id == merchant_id)
        .all()
    )


@router.get(
    "/{merchant_id}/geofences/{geofence_id}",
    response_model=schemas.GeofenceResponse,
)
def get_geofence(merchant_id: str, geofence_id: str, db: Session = Depends(get_db)):
    geo = (
        db.query(models.Geofence)
        .filter(
            models.Geofence.id == geofence_id,
            models.Geofence.merchant_id == merchant_id,
        )
        .first()
    )
    if not geo:
        raise HTTPException(status_code=404, detail="Geofence not found")
    return geo


@router.patch("/{merchant_id}/geofences/{geofence_id}/toggle", response_model=schemas.GeofenceResponse)
def toggle_geofence(
    merchant_id: str,
    geofence_id: str,
    db: Session = Depends(get_db),
    merchant: models.Merchant = Depends(get_merchant),
):
    if merchant.id != merchant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    geo = (
        db.query(models.Geofence)
        .filter(
            models.Geofence.id == geofence_id,
            models.Geofence.merchant_id == merchant_id,
        )
        .first()
    )
    if not geo:
        raise HTTPException(status_code=404, detail="Geofence not found")
    geo.is_active = not geo.is_active
    db.commit()
    db.refresh(geo)
    return geo


@router.delete("/{merchant_id}/geofences/{geofence_id}", status_code=204)
def delete_geofence(
    merchant_id: str,
    geofence_id: str,
    db: Session = Depends(get_db),
    merchant: models.Merchant = Depends(get_merchant),
):
    if merchant.id != merchant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    geo = (
        db.query(models.Geofence)
        .filter(
            models.Geofence.id == geofence_id,
            models.Geofence.merchant_id == merchant_id,
        )
        .first()
    )
    if not geo:
        raise HTTPException(status_code=404, detail="Geofence not found")
    db.delete(geo)
    db.commit()
