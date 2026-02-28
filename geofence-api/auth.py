from fastapi import HTTPException, Security, Depends
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session

from database import get_db
import models

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


async def get_merchant(
    api_key: str = Security(API_KEY_HEADER),
    db: Session = Depends(get_db),
) -> models.Merchant:
    if not api_key:
        raise HTTPException(status_code=401, detail="X-API-Key header required")

    merchant = db.query(models.Merchant).filter(models.Merchant.api_key == api_key).first()
    if not merchant:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return merchant
