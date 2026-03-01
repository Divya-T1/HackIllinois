from sqlalchemy import (
    Column, String, Float, Integer, Boolean, DateTime, ForeignKey, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

def utcnow():
    return datetime.now(timezone.utc)
from uuid import uuid4

from database import Base


class Merchant(Base):
    __tablename__ = "merchants"

    id = Column(String, primary_key=True, default=lambda: f"mer_{uuid4().hex[:12]}")
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    api_key = Column(String, unique=True, nullable=False, default=lambda: f"gf_{uuid4().hex}")
    stripe_account_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    geofences = relationship("Geofence", back_populates="merchant", cascade="all, delete-orphan")
    customers = relationship("Customer", back_populates="merchant")
    offers = relationship("Offer", back_populates="merchant")


class Geofence(Base):
    __tablename__ = "geofences"

    id = Column(String, primary_key=True, default=lambda: f"geo_{uuid4().hex[:12]}")
    merchant_id = Column(String, ForeignKey("merchants.id"), nullable=False)
    name = Column(String, nullable=False)
    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)
    radius_meters = Column(Float, default=75.0)
    max_discount = Column(Integer, default=20)
    active_hours_start = Column(String, default="07:00")
    active_hours_end = Column(String, default="20:00")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)

    merchant = relationship("Merchant", back_populates="geofences")
    discount_tiers = relationship(
        "DiscountTier", back_populates="geofence", cascade="all, delete-orphan"
    )
    offers = relationship("Offer", back_populates="geofence")
    checkins = relationship("CheckinEvent", back_populates="geofence")


class DiscountTier(Base):
    __tablename__ = "discount_tiers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    geofence_id = Column(String, ForeignKey("geofences.id"), nullable=False)
    # new_customer | frequent_visitor | lapsed_customer | regular
    tier_type = Column(String, nullable=False)
    percent = Column(Integer, nullable=False)

    geofence = relationship("Geofence", back_populates="discount_tiers")


class Customer(Base):
    __tablename__ = "customers"

    id = Column(String, primary_key=True, default=lambda: f"cus_{uuid4().hex[:12]}")
    merchant_id = Column(String, ForeignKey("merchants.id"), nullable=False)
    external_user_id = Column(String, nullable=False)
    first_seen = Column(DateTime, default=utcnow)
    last_seen = Column(DateTime, nullable=True)
    total_visits = Column(Integer, default=0)
    avg_spend = Column(Float, default=0.0)

    merchant = relationship("Merchant", back_populates="customers")

    __table_args__ = (
        UniqueConstraint("merchant_id", "external_user_id", name="uq_merchant_customer"),
    )


class CheckinEvent(Base):
    __tablename__ = "checkin_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    merchant_id = Column(String, ForeignKey("merchants.id"), nullable=False)
    external_user_id = Column(String, nullable=False)
    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)
    geofence_id = Column(String, ForeignKey("geofences.id"), nullable=True)
    triggered = Column(Boolean, default=False)
    timestamp = Column(DateTime, default=utcnow)

    geofence = relationship("Geofence", back_populates="checkins")


class MerchantPromotion(Base):
    __tablename__ = "merchant_promotions"

    id = Column(String, primary_key=True, default=lambda: f"promo_{uuid4().hex[:12]}")
    company_id = Column(String, ForeignKey("merchants.id"), nullable=False)
    description = Column(String, nullable=False)
    timeline = Column(String, nullable=False)  # day | week | month
    created_at = Column(DateTime, default=utcnow)

    merchant = relationship("Merchant", backref="promotions")


class Offer(Base):
    __tablename__ = "offers"

    id = Column(String, primary_key=True, default=lambda: f"off_{uuid4().hex[:12]}")
    merchant_id = Column(String, ForeignKey("merchants.id"), nullable=False)
    geofence_id = Column(String, ForeignKey("geofences.id"), nullable=False)
    external_user_id = Column(String, nullable=False)
    discount_percent = Column(Integer, nullable=False)
    reason_code = Column(String, nullable=False)
    reason_explanation = Column(String, nullable=False)
    stripe_coupon_id = Column(String, nullable=True)
    stripe_payment_link = Column(String, nullable=True)
    # pending | redeemed | expired
    status = Column(String, default="pending")
    created_at = Column(DateTime, default=utcnow)
    redeemed_at = Column(DateTime, nullable=True)

    merchant = relationship("Merchant", back_populates="offers")
    geofence = relationship("Geofence", back_populates="offers")
