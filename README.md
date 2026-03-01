# Geofence API

A **Stripe-native geofence API** that allows merchants to define promotional policies and automatically trigger personalized, location-based payment links when customers enter a physical zone.

---

## Features

- **Geofence Detection** — Haversine-based distance math to determine when a user enters a defined circular zone
- **Smart Customer Classification** — Automatically segments customers into `new_customer`, `frequent_visitor`, `lapsed_customer`, or `regular` based on visit history
- **Personalized Discounts** — Per-geofence discount tiers are matched to customer segments and capped at a merchant-configured maximum
- **Stripe Integration** — Automatically creates Stripe Coupons and Payment Links inside a merchant's connected account; falls back to mock URLs in dev mode
- **Offer Cooldowns** — Prevents offer spam with a 6-hour cooldown per user per merchant
- **Active Hours** — Geofences only fire offers within merchant-configured time windows (America/Chicago timezone)
- **Webhook Support** — Listens for `checkout.session.completed` Stripe events to mark offers as redeemed
- **Analytics** — Per-merchant offer counts, redemption totals, and conversion rates
- **Promotions** — Merchants can register time-scoped promotional campaigns (`day` / `week` / `month`)

---

## Tech Stack

| Layer | Technology |
|---|---|
| API Framework | [FastAPI](https://fastapi.tiangolo.com/) |
| ORM | [SQLAlchemy](https://www.sqlalchemy.org/) |
| Database | SQLite (dev) / PostgreSQL (prod) |
| Payments | [Stripe](https://stripe.com/) |
| HTTP Client | [httpx](https://www.python-httpx.org/) |
| AI (optional) | [Anthropic Claude](https://www.anthropic.com/) |
| Server | [Uvicorn](https://www.uvicorn.org/) |

---

## Getting Started

### Prerequisites

- Python 3.10+
- A [Stripe](https://stripe.com/) account (optional for dev/mock mode)

### Installation

```bash
git clone https://github.com/Divya-T1/HackIllinois.git
cd HackIllinois
pip install -r requirements.txt
```

### Environment Variables

Create a `.env` file in the project root:

```env
# Database (defaults to SQLite if not set)
DATABASE_URL=sqlite:///./geofence.db

# Stripe (leave blank to run in mock mode)
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
DEFAULT_PRICE_ID=price_...

# Anthropic (optional)
ANTHROPIC_API_KEY=sk-ant-...
```

### Running the Server

```bash
uvicorn main:app --reload
```

The API will be available at `http://localhost:8000`. Interactive docs are at `http://localhost:8000/docs`.

---

## 📡 API Overview

All authenticated routes require the `X-API-Key` header with a merchant's API key.

### Merchants
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/v1/merchants/` | Register a new merchant |
| `GET` | `/v1/merchants/` | List all merchants |
| `GET` | `/v1/merchants/{id}` | Get a merchant by ID |

### Geofences
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `POST` | `/v1/merchants/{id}/geofences` | ✅ | Create a geofence with discount tiers |
| `GET` | `/v1/merchants/{id}/geofences` | | List geofences for a merchant |
| `GET` | `/v1/merchants/{id}/geofences/{geo_id}` | | Get a specific geofence |
| `PATCH` | `/v1/merchants/{id}/geofences/{geo_id}/toggle` | ✅ | Enable/disable a geofence |
| `DELETE` | `/v1/merchants/{id}/geofences/{geo_id}` | ✅ | Delete a geofence |

### Check-ins & Offers
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/v1/checkins` | Submit a user location; triggers offer if inside a geofence |
| `GET` | `/v1/offers/{offer_id}` | Look up an offer by ID |

### Analytics
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/v1/merchants/{id}/analytics` | Get offer and redemption stats |

### Webhooks
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/v1/webhooks/stripe` | Stripe event receiver (marks offers as redeemed) |

### Promotions
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/v1/promotions/` | Create a promotion campaign |
| `GET` | `/v1/promotions/` | List all promotions |
| `GET` | `/v1/promotions/{company_id}` | Get promotions for a merchant |

---

## Decision Engine

When a check-in is received, the engine follows these steps:

1. **Geofence match** — finds the closest active geofence containing the user's coordinates
2. **Active hours check** — verifies the current time is within the geofence's operating window
3. **Cooldown check** — skips if the user already received an offer within 6 hours
4. **Customer classification** — assigns a tier based on visit history:
   - `new_customer` — first visit ever
   - `lapsed_customer` — no visit in 30+ days
   - `frequent_visitor` — 3+ visits in the last 7 days
   - `regular` — everyone else
5. **Discount selection** — picks the matching discount tier, capped at the geofence's `max_discount`
6. **Stripe offer creation** — generates a Coupon + Payment Link (or a mock in dev mode)
7. **Offer persistence** — saves the offer and updates the customer's visit record

---

## 📁 Project Structure

```
.
├── main.py          # FastAPI app entry point
├── database.py      # SQLAlchemy engine & session setup
├── models.py        # ORM models (Merchant, Geofence, Offer, etc.)
├── engine.py        # Geofence math + decision engine + Stripe integration
├── auth.py          # API key authentication dependency
├── merchants.py     # Merchant CRUD routes
├── geofences.py     # Geofence CRUD routes
├── checkins.py      # Check-in processing & offer generation
├── analytics.py     # Analytics routes
├── webhooks.py      # Stripe webhook handler
├── promotions.py    # Promotion campaign routes
├── requirements.txt
└── geofence.db      # SQLite database (auto-created on first run)
```

---

## Example: Triggering an Offer

```bash
# 1. Register a merchant
curl -X POST http://localhost:8000/v1/merchants/ \
  -H "Content-Type: application/json" \
  -d '{"name": "Coffee House", "email": "owner@coffeehouse.com"}'

# 2. Create a geofence (use the api_key from step 1)
curl -X POST http://localhost:8000/v1/merchants/{merchant_id}/geofences \
  -H "X-API-Key: gf_your_api_key" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Main St Location",
    "lat": 40.1106,
    "lng": -88.2073,
    "radius_meters": 75,
    "max_discount": 20,
    "active_hours": {"start": "07:00", "end": "20:00"},
    "discount_tiers": [
      {"type": "new_customer", "percent": 20},
      {"type": "lapsed_customer", "percent": 15},
      {"type": "frequent_visitor", "percent": 10},
      {"type": "regular", "percent": 5}
    ]
  }'

# 3. Submit a check-in
curl -X POST "http://localhost:8000/v1/checkins?merchant_id={merchant_id}" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user_abc123", "lat": 40.1106, "lng": -88.2073}'
```

---

## License

MIT