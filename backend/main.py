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

async def _startup():
    from data.db import init_db
    try:
        await init_db()
    except Exception as e:
        print(f"[startup] DB init failed: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(_startup())
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


@app.get("/api/test-data-gov", tags=["Health"])
async def test_data_gov():
    """Test if data.gov.in API is reachable from this server."""
    import httpx, os
    url = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"
    params = {
        "api-key": os.getenv("DATA_GOV_API_KEY", ""),
        "format": "json",
        "limit": "2",
        "filters[commodity]": "Onion",
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, params=params)
            return {
                "status": resp.status_code,
                "records_count": len(resp.json().get("records", [])),
                "reachable": True,
            }
    except Exception as e:
        return {"reachable": False, "error": type(e).__name__, "detail": str(e)}
