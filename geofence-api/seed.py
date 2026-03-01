"""
Seed script — creates realistic fake merchants for downtown Champaign, IL.

Run once:
    cd geofence-api
    python seed.py

Merchants:
  • Suzu's Bakery        — downtown Champaign bakery  ← great for live demo
  • Espresso Royale      — Green Street coffee shop
  • Boltini Lounge       — Neil Street cocktail bar
  • Cowboy Monkey        — Downtown live-music venue
  • Maize Mexican Grill  — Green Street fast-casual
  • Seven Saints         — Chester Street bar & kitchen

Demo customers (seeded against Suzu's Bakery):
  • user_demo_01  → frequent_visitor  (3 triggered checkins in the last 7 days)
  • user_demo_02  → regular           (2 total visits, last seen yesterday)
  • user_demo_03  → lapsed_customer   (last seen 45 days ago)
"""

from datetime import datetime, timedelta, timezone
from database import SessionLocal, engine, Base
import models

Base.metadata.create_all(bind=engine)

MERCHANTS: list[dict] = [
    {
        "name": "Suzu's Bakery",
        "email": "hello@suzusbakery-demo.com",
        "geofences": [
            {
                "name": "Main Entrance",
                "lat": 40.11680,
                "lng": -88.24215,
                "radius_meters": 80,
                "max_discount": 25,
                "active_hours_start": "2:00",
                "active_hours_end": "23:59",
                "tiers": [
                    {"tier_type": "new_customer",     "percent": 15},
                    {"tier_type": "frequent_visitor", "percent": 25},
                    {"tier_type": "lapsed_customer",  "percent": 20},
                    {"tier_type": "regular",          "percent": 10},
                ],
            }
        ],
    },
    {
        "name": "Espresso Royale",
        "email": "owner@espressoroyale-demo.com",
        "geofences": [
            {
                "name": "Green Street Entrance",
                "lat": 40.10982,
                "lng": -88.22814,
                "radius_meters": 80,
                "max_discount": 20,
                "active_hours_start": "02:00",
                "active_hours_end": "23:59",
                "tiers": [
                    {"tier_type": "new_customer",     "percent": 15},
                    {"tier_type": "frequent_visitor", "percent": 20},
                    {"tier_type": "lapsed_customer",  "percent": 20},
                    {"tier_type": "regular",          "percent": 10},
                ],
            }
        ],
    },
    {
        "name": "Boltini Lounge",
        "email": "contact@boltini-demo.com",
        "geofences": [
            {
                "name": "Neil Street Entrance",
                "lat": 40.11615,
                "lng": -88.24225,
                "radius_meters": 60,
                "max_discount": 25,
                "active_hours_start": "2:00",
                "active_hours_end": "23:59",
                "tiers": [
                    {"tier_type": "new_customer",     "percent": 15},
                    {"tier_type": "frequent_visitor", "percent": 25},
                    {"tier_type": "lapsed_customer",  "percent": 20},
                    {"tier_type": "regular",          "percent": 10},
                ],
            }
        ],
    },
    {
        "name": "Cowboy Monkey",
        "email": "hello@cowboymonkey-demo.com",
        "geofences": [
            {
                "name": "Main Entrance",
                "lat": 40.11492,
                "lng": -88.23918,
                "radius_meters": 70,
                "max_discount": 15,
                "active_hours_start": "2:00",
                "active_hours_end": "23:59",
                "tiers": [
                    {"tier_type": "new_customer",     "percent": 10},
                    {"tier_type": "frequent_visitor", "percent": 15},
                    {"tier_type": "lapsed_customer",  "percent": 15},
                ],
            }
        ],
    },
    {
        "name": "Maize Mexican Grill",
        "email": "info@maizechampaign-demo.com",
        "geofences": [
            {
                "name": "Green Street Location",
                "lat": 40.10955,
                "lng": -88.22905,
                "radius_meters": 75,
                "max_discount": 20,
                "active_hours_start": "2:00",
                "active_hours_end": "23:59",
                "tiers": [
                    {"tier_type": "new_customer",     "percent": 10},
                    {"tier_type": "frequent_visitor", "percent": 15},
                    {"tier_type": "lapsed_customer",  "percent": 20},
                    {"tier_type": "regular",          "percent": 5},
                ],
            }
        ],
    },
    {
        "name": "Seven Saints",
        "email": "seven@sevensaints-demo.com",
        "geofences": [
            {
                "name": "Chester Street Patio",
                "lat": 40.11552,
                "lng": -88.24212,
                "radius_meters": 65,
                "max_discount": 20,
                "active_hours_start": "2:00",
                "active_hours_end": "23:59",
                "tiers": [
                    {"tier_type": "new_customer",     "percent": 10},
                    {"tier_type": "frequent_visitor", "percent": 20},
                    {"tier_type": "lapsed_customer",  "percent": 15},
                ],
            }
        ],
    },
]


# ── Demo customer profiles ──────────────────────────────────────────────────

# (lat, lng) right inside Suzu's Bakery geofence
SUZU_LAT = 40.11680
SUZU_LNG = -88.24215

DEMO_CUSTOMERS = [
    {
        # Classified as: frequent_visitor (>=3 triggered checkins in past 7 days)
        # Loyalty tier: silver (30 tokens -> +5pp bonus)
        "user_id": "user_demo_01",
        "total_visits": 5,
        "last_seen_delta_days": 0,
        "checkin_days_ago": [1, 3, 5],
        "loyalty_tokens": 30,
        "loyalty_tier": "silver",
    },
    {
        # Classified as: regular (recent, but <3 visits this week)
        # Loyalty tier: bronze (12 tokens -> +2pp bonus)
        "user_id": "user_demo_02",
        "total_visits": 2,
        "last_seen_delta_days": 1,
        "checkin_days_ago": [8],
        "loyalty_tokens": 12,
        "loyalty_tier": "bronze",
    },
    {
        # Classified as: lapsed_customer (last seen 45 days ago)
        # Loyalty tier: none (2 tokens after decay)
        "user_id": "user_demo_03",
        "total_visits": 3,
        "last_seen_delta_days": 45,
        "checkin_days_ago": [],
        "loyalty_tokens": 2,
        "loyalty_tier": "none",
    },
]


def seed_merchants(db) -> dict[str, str]:
    """Seed merchants. Returns {email: merchant_id}."""
    merchant_ids: dict[str, str] = {}
    for m_data in MERCHANTS:
        existing = db.query(models.Merchant).filter(models.Merchant.email == m_data["email"]).first()
        if existing:
            print(f"  skip  {m_data['name']} (already seeded)")
            merchant_ids[m_data["email"]] = existing.id
            continue

        merchant = models.Merchant(name=m_data["name"], email=m_data["email"])
        db.add(merchant)
        db.flush()
        merchant_ids[m_data["email"]] = merchant.id

        for g_data in m_data["geofences"]:
            geo = models.Geofence(
                merchant_id=merchant.id,
                name=g_data["name"],
                lat=g_data["lat"],
                lng=g_data["lng"],
                radius_meters=g_data["radius_meters"],
                max_discount=g_data["max_discount"],
                active_hours_start=g_data["active_hours_start"],
                active_hours_end=g_data["active_hours_end"],
            )
            db.add(geo)
            db.flush()

            for t in g_data["tiers"]:
                db.add(
                    models.DiscountTier(
                        geofence_id=geo.id,
                        tier_type=t["tier_type"],
                        percent=t["percent"],
                    )
                )

        db.commit()
        print(f"  ✓  {merchant.name}")
        print(f"       id      : {merchant.id}")
        print(f"       api_key : {merchant.api_key}")

    return merchant_ids


def seed_demo_customers(db, suzu_id: str) -> None:
    """Seed demo customer histories for Suzu's Bakery."""
    # Find Suzu's geofence for linking checkin events
    suzu_geo = (
        db.query(models.Geofence)
        .filter(models.Geofence.merchant_id == suzu_id)
        .first()
    )

    now = datetime.now(timezone.utc)

    for demo in DEMO_CUSTOMERS:
        uid = demo["user_id"]
        existing = (
            db.query(models.Customer)
            .filter(
                models.Customer.merchant_id == suzu_id,
                models.Customer.external_user_id == uid,
            )
            .first()
        )
        if existing:
            print(f"  skip  demo customer {uid} (already seeded)")
            continue

        last_seen = now - timedelta(days=demo["last_seen_delta_days"])

        # Seed realistic loyalty token counts so demo users show different tiers
        # user_demo_01 (frequent) -> silver (30 tokens)
        # user_demo_02 (regular)  -> bronze (12 tokens)
        # user_demo_03 (lapsed)   -> none   (2 tokens — decayed from inactivity)
        seed_tokens = demo.get("loyalty_tokens", 0)
        seed_tier   = demo.get("loyalty_tier", "none")

        customer = models.Customer(
            merchant_id=suzu_id,
            external_user_id=uid,
            first_seen=last_seen - timedelta(days=30),
            last_seen=last_seen,
            total_visits=demo["total_visits"],
            loyalty_tokens=seed_tokens,
            loyalty_tier=seed_tier,
        )
        db.add(customer)

        # Add triggered checkin events so visits_last_7_days count is correct
        for days_ago in demo["checkin_days_ago"]:
            ts = now - timedelta(days=days_ago)
            db.add(
                models.CheckinEvent(
                    merchant_id=suzu_id,
                    external_user_id=uid,
                    lat=SUZU_LAT,
                    lng=SUZU_LNG,
                    geofence_id=suzu_geo.id if suzu_geo else None,
                    triggered=True,
                    timestamp=ts,
                )
            )

        db.commit()
        print(f"  ✓  demo customer {uid}")


def seed() -> None:
    db = SessionLocal()
    try:
        print("\nSeeding merchants...\n")
        merchant_ids = seed_merchants(db)

        suzu_id = merchant_ids.get("hello@suzusbakery-demo.com")
        if suzu_id:
            print("\nSeeding demo customers for Suzu's Bakery...\n")
            seed_demo_customers(db, suzu_id)
        else:
            print("\nCould not find Suzu's Bakery — skipping demo customers.\n")

    finally:
        db.close()


if __name__ == "__main__":
    seed()
    print("\nDone.\n")
    print("Demo user IDs to test with:")
    print("  user_demo_01  →  frequent_visitor  (25% off)")
    print("  user_demo_02  →  regular           (10% off)")
    print("  user_demo_03  →  lapsed_customer   (20% off)")
    print()
    print("Use Suzu's Bakery coords in the frontend:")
    print(f"  lat={SUZU_LAT}, lng={SUZU_LNG}")