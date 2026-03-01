import hashlib

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
import models, schemas

router = APIRouter()


def _hash(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


@router.post("/register", response_model=schemas.UserResponse, status_code=201)
def register(payload: schemas.UserRegister, db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.username == payload.username).first():
        raise HTTPException(status_code=409, detail="Username already taken")
    if payload.role not in ("merchant", "customer"):
        raise HTTPException(status_code=400, detail="Role must be 'merchant' or 'customer'")
    user = models.User(username=payload.username, password_hash=_hash(payload.password), role=payload.role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=schemas.UserResponse)
def login(payload: schemas.UserLogin, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == payload.username).first()
    if not user or user.password_hash != _hash(payload.password):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return user


@router.get("/me/{user_id}", response_model=schemas.UserResponse)
def get_me(user_id: str, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Session expired")
    return user


@router.patch("/me/{user_id}/link-merchant")
def link_merchant(user_id: str, merchant_id: str, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.merchant_id = merchant_id
    user.role = "merchant"
    db.commit()
    return {"ok": True}
