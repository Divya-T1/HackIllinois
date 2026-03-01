from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime


# ── Merchant ─────────────────────────────────────────────────────────────────

class MerchantCreate(BaseModel):
    name: str
    email: EmailStr


class MerchantResponse(BaseModel):
    id: str
    name: str
    email: str
    api_key: str
    stripe_account_id: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Discount tiers ────────────────────────────────────────────────────────────

class DiscountTierCreate(BaseModel):
    type: str   # new_customer | frequent_visitor | lapsed_customer | regular
    percent: int


class DiscountTierResponse(BaseModel):
    id: int
    tier_type: str
    percent: int

    model_config = {"from_attributes": True}


# ── Geofence ──────────────────────────────────────────────────────────────────

class ActiveHours(BaseModel):
    start: str = "00:00"
    end: str = "23:59"


class GeofenceCreate(BaseModel):
    name: str
    lat: float
    lng: float
    radius_meters: float = 75.0
    discount_tiers: List[DiscountTierCreate]
    max_discount: int = 20
    active_hours: ActiveHours = ActiveHours()


class GeofenceResponse(BaseModel):
    id: str
    merchant_id: str
    name: str
    lat: float
    lng: float
    radius_meters: float
    max_discount: int
    active_hours_start: str
    active_hours_end: str
    is_active: bool
    discount_tiers: List[DiscountTierResponse]
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Checkin / Offer ───────────────────────────────────────────────────────────

class CheckinRequest(BaseModel):
    user_id: str
    lat: float
    lng: float
    merchant_id: Optional[str] = None   # required when not using API key auth


class OfferPersonalization(BaseModel):
    reason_code: str
    explanation: str


class LoyaltyStatus(BaseModel):
    """Loyalty snapshot returned with every triggered offer."""
    tier: str          # none | bronze | silver | gold | platinum
    tokens: int        # token balance after this visit
    bonus_pp: int      # extra percentage points added on top of base discount
    base_percent: int  # base discount before loyalty bonus was applied


class CheckinResponse(BaseModel):
    offer_id: Optional[str] = None
    enabled: bool
    discount_percent: Optional[int] = None
    personalization: Optional[OfferPersonalization] = None
    loyalty: Optional[LoyaltyStatus] = None
    stripe_payment_link: Optional[str] = None
    geofence_name: Optional[str] = None
    message: str


# ── Promotions ────────────────────────────────────────────────────────────────

class PromotionCreate(BaseModel):
    company_id: str
    description: str
    timeline: str  # day | week | month


class PromotionResponse(BaseModel):
    id: str
    company_id: str
    description: str
    timeline: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Auth ──────────────────────────────────────────────────────────────────────

class UserRegister(BaseModel):
    username: str
    password: str
    role: str  # merchant | customer


class UserLogin(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    id: str
    username: str
    role: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Analytics ─────────────────────────────────────────────────────────────────

class AnalyticsResponse(BaseModel):
    merchant_id: str
    total_offers: int
    redeemed_offers: int
    redemption_rate: float
    total_revenue: float
    conversion_percent: float