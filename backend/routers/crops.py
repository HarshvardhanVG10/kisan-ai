"""
GET /api/recommend?district=&season=
Returns top 3 recommended crops with reasoning, and crops to avoid with reasoning.
Scoring based on: price trend, seasonality, weather risk, historical volatility.

Uses real price history from data.gov.in and real weather from Open-Meteo.
Never uses mock price history.
If a crop has < 7 real history records, price/volatility scoring is skipped (neutral 50).
data_quality per crop: "full_live" | "limited_live" | "no_price_data"
"""

from fastapi import APIRouter, Query
from typing import Optional, List, Dict
import numpy as np
from datetime import datetime
from data.mock_data import CROPS, CROP_CONFIG
from data.real_prices import fetch_all_history
from routers.weather import get_weather_risk_score, _generate_10day_forecast, _compute_overall_risk

router = APIRouter()

# Seasonal crop suitability: which crops are appropriate for which season
SEASON_SUITABILITY = {
    "Kharif": {  # June–October (Monsoon)
        "Onion":   0.5,
        "Tomato":  0.8,
        "Potato":  0.3,
        "Wheat":   0.0,
        "Rice":    1.0,
        "Soybean": 1.0,
        "Cotton":  1.0,
        "Maize":   0.9,
        "Garlic":  0.2,
        "Chilli":  0.7,
    },
    "Rabi": {  # November–March (Winter)
        "Onion":   0.9,
        "Tomato":  0.7,
        "Potato":  1.0,
        "Wheat":   1.0,
        "Rice":    0.3,
        "Soybean": 0.2,
        "Cotton":  0.1,
        "Maize":   0.5,
        "Garlic":  1.0,
        "Chilli":  0.6,
    },
    "Zaid": {  # March–May (Summer)
        "Onion":   0.6,
        "Tomato":  0.6,
        "Potato":  0.5,
        "Wheat":   0.2,
        "Rice":    0.5,
        "Soybean": 0.3,
        "Cotton":  0.4,
        "Maize":   0.7,
        "Garlic":  0.4,
        "Chilli":  0.5,
    },
}


def _score_crop(
    crop: str,
    district: Optional[str],
    season: str,
    weather_risk_score: int,
    real_history: Optional[list] = None,
) -> Dict:
    """
    Score a crop on multiple dimensions and return score breakdown with reasons.
    Uses real history if >= 7 records; otherwise neutral price/volatility scoring.
    """
    data_quality = "no_price_data"
    price_score = 50.0      # neutral default
    volatility_score = 50.0  # neutral default
    current_price = 0.0
    price_trend_30d = 0.0

    if real_history and len(real_history) >= 7:
        prices_all = [r["price"] for r in real_history]
        n = len(prices_all)
        prices_30d = np.array(prices_all[max(0, n - 30):])
        prices_7d  = np.array(prices_all[max(0, n - 7):])

        current_price = float(prices_30d[-1])
        price_trend_30d = ((prices_30d[-1] - prices_30d[0]) / max(prices_30d[0], 1)) * 100
        price_trend_7d  = ((prices_7d[-1]  - prices_7d[0])  / max(prices_7d[0], 1))  * 100

        # Price score: higher trend = better for seller
        price_score = min(100, max(0, 50 + price_trend_30d * 2 + price_trend_7d))

        # Volatility score: lower CV = higher score
        cv = float(np.std(prices_30d) / max(np.mean(prices_30d), 1))
        volatility_score = max(0, 100 - cv * 300)

        data_quality = "full_live"
    elif real_history and len(real_history) >= 1:
        current_price = float(real_history[-1]["price"])
        data_quality = "limited_live"
        # price_score and volatility_score stay at neutral 50

    # Arrival trend score: not available from data.gov.in history → neutral
    arrival_score = 50.0

    # Seasonal suitability score (0–100)
    season_score = SEASON_SUITABILITY.get(season, {}).get(crop, 0.5) * 100

    # Weather risk penalty (0–100): lower weather risk = higher score
    weather_score = max(0, 100 - weather_risk_score)

    composite = (
        price_score      * 0.30
        + volatility_score * 0.20
        + arrival_score    * 0.20
        + season_score     * 0.20
        + weather_score    * 0.10
    )

    # Build reasons list
    reasons: List[str] = []
    if data_quality == "full_live":
        if price_trend_30d > 10:
            reasons.append(f"Price trending up {price_trend_30d:.1f}% over last 30 days — strong momentum")
        elif price_trend_30d > 5:
            reasons.append(f"Price up {price_trend_30d:.1f}% over 30 days — moderate uptrend")
        elif price_trend_30d < -10:
            reasons.append(f"Price falling {abs(price_trend_30d):.1f}% over 30 days — bearish signal")
        else:
            reasons.append(f"Price relatively stable ({price_trend_30d:+.1f}% over 30 days)")
    elif data_quality == "limited_live":
        reasons.append("Limited price data — trend analysis not available")
    else:
        reasons.append("No live price data available from Agmarknet for this crop")

    suitability = SEASON_SUITABILITY.get(season, {}).get(crop, 0.5)
    if suitability >= 0.8:
        reasons.append(f"Excellent {season} season crop — historically strong performance")
    elif suitability >= 0.5:
        reasons.append(f"Moderate {season} suitability — can be grown with proper management")
    elif suitability < 0.3:
        reasons.append(f"Not ideal for {season} season — unfavorable growing conditions")

    if weather_risk_score > 60:
        reasons.append("High weather risk in your district — crop loss possible")
    elif weather_risk_score < 30:
        reasons.append("Weather risk low in your district — favourable conditions")

    return {
        "crop":             crop,
        "composite_score":  round(composite, 1),
        "price_score":      round(price_score, 1),
        "volatility_score": round(volatility_score, 1),
        "arrival_score":    round(arrival_score, 1),
        "season_score":     round(season_score, 1),
        "weather_score":    round(weather_score, 1),
        "current_price":    round(current_price, 2),
        "price_trend_30d":  round(float(price_trend_30d), 2),
        "reasons":          reasons,
        "data_source":      "live" if data_quality in ("full_live", "limited_live") else "unavailable",
        "data_quality":     data_quality,
        "data_limited":     data_quality != "full_live",
    }


@router.get("/recommend")
async def get_recommendations(
    district: Optional[str] = Query(None),
    season: str = Query("Kharif", regex="^(Kharif|Rabi|Zaid)$"),
):
    """
    Returns top 3 recommended crops and crops to avoid for the given district and season.
    Uses real historical prices from data.gov.in and real weather from Open-Meteo.
    """
    effective_district = district or "Nashik"

    # Fetch real weather risk score (async, real API)
    weather_data_source = "mock"
    try:
        weather_risk_score = await get_weather_risk_score(effective_district)
        weather_data_source = "live"
    except Exception as e:
        print(f"[crops] Could not fetch weather risk: {e}")
        weather_forecast   = _generate_10day_forecast(effective_district)
        weather_overall    = _compute_overall_risk(weather_forecast)
        weather_risk_score = weather_overall["risk_score"]

    # Fetch real price history for all crops concurrently
    all_history: dict = {}
    try:
        all_history = await fetch_all_history(district, days=60)
    except Exception as e:
        print(f"[crops] Could not fetch price history: {e}")

    # Score all crops
    scored = []
    for crop in CROPS:
        real_history = all_history.get(crop, [])
        score_data = _score_crop(crop, district, season, weather_risk_score, real_history)
        scored.append(score_data)

    # Sort by composite score
    scored.sort(key=lambda x: x["composite_score"], reverse=True)

    top_3 = scored[:3]
    avoid_candidates = [c for c in scored[-3:] if c["composite_score"] < 40]
    if not avoid_candidates:
        avoid_candidates = scored[-2:]

    # Enrich avoid crops with avoid reasons
    for crop_data in avoid_candidates:
        avoid_reasons = []
        if crop_data["price_trend_30d"] < -5:
            avoid_reasons.append(f"Price falling {abs(crop_data['price_trend_30d']):.1f}% — poor market")
        if crop_data["season_score"] < 30:
            avoid_reasons.append(f"Poorly suited to {season} season")
        if crop_data["volatility_score"] < 30:
            avoid_reasons.append("Highly volatile prices — income risk high")
        if crop_data["weather_score"] < 40:
            avoid_reasons.append("Weather risk too high for this crop this season")
        if crop_data["data_quality"] == "no_price_data":
            avoid_reasons.append("No live price data available — cannot assess market conditions")
        if not avoid_reasons:
            avoid_reasons.append(
                f"Lower scoring crop relative to alternatives ({crop_data['composite_score']:.0f}/100)"
            )
        crop_data["avoid_reasons"] = avoid_reasons

    # Overall data quality summary
    full_live_count = sum(1 for c in scored if c["data_quality"] == "full_live")
    overall_ds = "live" if full_live_count > 0 else "no_price_data"

    return {
        "district":            district or "All",
        "season":              season,
        "weather_risk_level":  (
            "high" if weather_risk_score > 65 else "medium" if weather_risk_score > 35 else "low"
        ),
        "weather_data_source": weather_data_source,
        "data_source":         overall_ds,
        "crops_with_full_data": full_live_count,
        "crops_with_limited_data": sum(1 for c in scored if c["data_quality"] == "limited_live"),
        "crops_with_no_data":  sum(1 for c in scored if c["data_quality"] == "no_price_data"),
        "recommendations": [
            {
                "rank":            i + 1,
                "crop":            c["crop"],
                "score":           c["composite_score"],
                "current_price":   c["current_price"],
                "price_trend_30d": c["price_trend_30d"],
                "reasons":         c["reasons"],
                "data_source":     c["data_source"],
                "data_quality":    c["data_quality"],
                "data_limited":    c["data_limited"],
            }
            for i, c in enumerate(top_3)
        ],
        "avoid": [
            {
                "crop":          c["crop"],
                "score":         c["composite_score"],
                "reasons":       c.get("avoid_reasons", []),
                "data_source":   c["data_source"],
                "data_quality":  c["data_quality"],
            }
            for c in avoid_candidates
        ],
        "disclaimer": (
            "Recommendations are based on live Agmarknet price data, seasonal patterns, "
            "and weather forecasts. Crops marked data_quality='no_price_data' use neutral "
            "price scoring. Always consult local agricultural officers before making planting decisions."
        ),
    }
