"""
Seed script — creates realistic fake merchants for downtown Champaign, IL.

Run once:
    cd geofence-api
    python seed.py

Merchants created (all real locations in Champaign/Urbana):
  • Espresso Royale       — Green Street coffee shop
  • Boltini Lounge        — Neil Street cocktail bar
  • Cowboy Monkey         — Downtown live-music venue
  • Maize Mexican Grill   — Green Street fast-casual
  • Seven Saints          — Chester Street bar & kitchen
"""

from database import SessionLocal, engine, Base
import models

Base.metadata.create_all(bind=engine)

MERCHANTS: list[dict] = [
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
                "active_hours_start": "06:00",
                "active_hours_end": "22:00",
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
                "active_hours_start": "11:00",
                "active_hours_end": "23:00",
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
                "active_hours_start": "18:00",
                "active_hours_end": "23:00",
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
                "active_hours_start": "10:00",
                "active_hours_end": "21:00",
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
                "active_hours_start": "10:00",
                "active_hours_end": "23:00",
                "tiers": [
                    {"tier_type": "new_customer",     "percent": 10},
                    {"tier_type": "frequent_visitor", "percent": 20},
                    {"tier_type": "lapsed_customer",  "percent": 15},
                ],
            }
        ],
    },
]


def seed() -> None:
    db = SessionLocal()
    try:
        for m_data in MERCHANTS:
            if db.query(models.Merchant).filter(models.Merchant.email == m_data["email"]).first():
                print(f"  skip  {m_data['name']} (already seeded)")
                continue

            merchant = models.Merchant(name=m_data["name"], email=m_data["email"])
            db.add(merchant)
            db.flush()

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

    finally:
        db.close()


if __name__ == "__main__":
    print("\nSeeding downtown Champaign merchants...\n")
    seed()
    print("\nDone. Copy any api_key above to use as X-API-Key header.\n")
