import hashlib

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
import models
import schemas

router = APIRouter()


def _hash(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


@router.post("/register", response_model=schemas.UserResponse, status_code=201)
def register(body: schemas.UserRegister, db: Session = Depends(get_db)):
    if body.role not in ("merchant", "customer"):
        raise HTTPException(status_code=400, detail="Role must be 'merchant' or 'customer'")
    if len(body.username.strip()) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters")
    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    existing = db.query(models.User).filter(models.User.username == body.username).first()
    if existing:
        raise HTTPException(status_code=409, detail="Username already taken")

    user = models.User(
        username=body.username.strip(),
        password_hash=_hash(body.password),
        role=body.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=schemas.UserResponse)
def login(body: schemas.UserLogin, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == body.username).first()
    if not user or user.password_hash != _hash(body.password):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return user
