from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import os

from database import engine, Base
from routers import merchants, geofences, checkins, analytics, webhooks, promotions

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Geofence Offer Engine",
    description=(
        "A Stripe-native geofence API that allows merchants to define promotional "
        "policies and automatically trigger personalized, location-based payment "
        "links when customers enter a physical zone."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(merchants.router, prefix="/v1/merchants", tags=["merchants"])
app.include_router(geofences.router, prefix="/v1/merchants", tags=["geofences"])
app.include_router(checkins.router, prefix="/v1", tags=["checkins"])
app.include_router(analytics.router, prefix="/v1/merchants", tags=["analytics"])
app.include_router(webhooks.router, prefix="/v1/webhooks", tags=["webhooks"])
app.include_router(promotions.router, prefix="/v1/promotions", tags=["promotions"])


# ── Routes that must be registered BEFORE the catch-all static mount ─────────

@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}


@app.get("/demo/checkout/{mock_id}", response_class=HTMLResponse, tags=["meta"])
def mock_checkout(mock_id: str):
    """Local stand-in for Stripe Checkout — shown when no price_id is configured."""
    return HTMLResponse(content=f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>Demo Checkout</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
         background:#f6f9fc;display:flex;align-items:center;justify-content:center;min-height:100vh}}
    .card{{background:#fff;border-radius:8px;box-shadow:0 4px 24px rgba(0,0,0,.08);
           padding:40px;max-width:420px;width:100%;text-align:center}}
    .badge{{display:inline-block;background:#ede9fe;color:#6d28d9;border-radius:20px;
            padding:4px 12px;font-size:12px;font-weight:600;letter-spacing:.5px;margin-bottom:20px}}
    h1{{font-size:22px;color:#1a1a2e;margin-bottom:8px}}
    p{{color:#6b7280;font-size:14px;line-height:1.6;margin-bottom:24px}}
    button{{width:100%;background:#635bff;color:#fff;border:none;border-radius:6px;
            padding:14px;font-size:16px;font-weight:600;cursor:pointer;transition:background .2s}}
    button:hover{{background:#4f46e5}}
    .note{{margin-top:16px;font-size:12px;color:#9ca3af}}
    .check{{font-size:48px;margin-bottom:16px}}
  </style>
</head>
<body>
  <div class="card" id="pay-view">
    <div class="badge">DEMO MODE — no real charge</div>
    <h1>Geofence Offer Checkout</h1>
    <p>Add a real <code>price_...</code> ID to <code>.env</code> to get a live Stripe link.</p>
    <button onclick="document.getElementById('pay-view').style.display='none';
                     document.getElementById('ok-view').style.display='block'">
      Pay Now (Demo)
    </button>
    <div class="note">Offer ID: {mock_id[:20]}</div>
  </div>
  <div class="card" id="ok-view" style="display:none">
    <div class="check">✅</div>
    <h1>Payment Successful!</h1>
    <p>In production, Stripe fires a <code>checkout.session.completed</code> webhook
       which marks this offer as redeemed in the database.</p>
  </div>
</body>
</html>""")


# ── Static frontend — MUST come after all explicit routes ─────────────────────
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
