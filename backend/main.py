"""
KisanAI — Crop Intelligence Platform
FastAPI backend with CORS enabled.
"""

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import trends, forecast, weather, crops, risk, crops_list, msp
from data.real_prices import fetch_all_crops_real, fetch_all_history

TOP_DISTRICTS = ["Nashik", "Pune", "Nagpur", "Latur", "Aurangabad"]

async def _warm_cache():
    """Pre-fetch prices for top districts on startup so first requests are fast."""
    try:
        print("[startup] Warming price cache...")
        await asyncio.gather(
            *[fetch_all_crops_real(d) for d in TOP_DISTRICTS],
            return_exceptions=True
        )
        print("[startup] Cache warm complete.")
    except Exception as e:
        print(f"[startup] Cache warm failed: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(_warm_cache())
    yield

app = FastAPI(
    lifespan=lifespan,
    title="KisanAI Crop Intelligence API",
    description=(
        "Backend API for the KisanAI Crop Intelligence Platform. "
        "Provides price trends, forecasts, weather risk, crop recommendations, "
        "and risk analysis for Indian agricultural markets."
    ),
    version="1.0.0",
)

# Allow all origins for development (restrict in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(trends.router, prefix="/api", tags=["Trends"])
app.include_router(forecast.router, prefix="/api", tags=["Forecast"])
app.include_router(weather.router, prefix="/api", tags=["Weather"])
app.include_router(crops.router, prefix="/api", tags=["Recommendations"])
app.include_router(risk.router, prefix="/api", tags=["Risk"])
app.include_router(crops_list.router, prefix="/api", tags=["Crops"])
app.include_router(msp.router, prefix="/api", tags=["MSP"])


@app.get("/", tags=["Health"])
def root():
    return {
        "service": "KisanAI Crop Intelligence API",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "crops_list": "GET /api/crops",
            "trends": "GET /api/trends/{crop}?district=&days=30",
            "forecast": "GET /api/forecast/{crop}?days=30&district=",
            "weather": "GET /api/weather/{district}",
            "soil": "GET /api/soil/{district}",
            "recommendations": "GET /api/recommend?district=&season=Kharif",
            "risk": "GET /api/risk/{crop}?district=",
            "msp": "GET /api/msp/{crop}?district=&price=",
            "docs": "/docs",
        },
    }


@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "healthy"}
