from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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

# Serve the frontend if the directory exists
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}
