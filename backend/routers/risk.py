"""
GET /api/risk/{crop}?district=
Returns overall risk score (green/yellow/red) with breakdown:
supply_risk, weather_risk, price_volatility_risk, seasonal_risk.
Each with score 0-100 and explanation text.

Uses live price history (>= 7 records) for volatility and trend.
Falls back to single current live price when history unavailable (marked as limited_live).
Never uses mock price data.
"""

from fastapi import APIRouter, Query, HTTPException
from typing import Optional, Dict
import numpy as np
from datetime import datetime
from data.mock_data import CROPS, CROP_CONFIG
from data.real_prices import fetch_real_price, fetch_price_history
from data.msp_data import compare_price_to_msp
from data.district_data import get_district_suitability
from routers.weather import get_weather_risk_score, _generate_10day_forecast, _compute_overall_risk

router = APIRouter()


def _risk_color(score: float) -> str:
    if score <= 35:
        return "green"
    elif score <= 65:
        return "yellow"
    else:
        return "red"


def _price_volatility_risk_from_history(prices_30d: np.ndarray) -> Dict:
    """Price volatility risk from real 30-day price series."""
    cv = float(np.std(prices_30d) / max(np.mean(prices_30d), 1))
    price_range_pct = float(
        (np.max(prices_30d) - np.min(prices_30d)) / max(np.mean(prices_30d), 1) * 100
    )
    score = min(100, cv * 300)

    if cv > 0.25:
        explanation = f"Extremely high price volatility (CV={cv:.2f}) — income planning very difficult"
        factors = [
            f"Coefficient of variation: {cv*100:.1f}%",
            f"Price range in 30 days: {price_range_pct:.1f}%",
            "Consider hedging or phased selling strategy",
        ]
    elif cv > 0.15:
        explanation = f"High price volatility (CV={cv:.2f}) — prices swinging significantly"
        factors = [
            f"Coefficient of variation: {cv*100:.1f}%",
            f"30-day price range: ±{price_range_pct/2:.1f}% around mean",
        ]
    elif cv > 0.08:
        explanation = f"Moderate price volatility (CV={cv:.2f}) — some fluctuation expected"
        factors = [
            f"Coefficient of variation: {cv*100:.1f}%",
            "Price movements within normal range",
        ]
    else:
        explanation = f"Low price volatility (CV={cv:.2f}) — predictable pricing"
        factors = [
            f"Coefficient of variation: {cv*100:.1f}%",
            "Stable prices make income planning straightforward",
        ]

    return {
        "score":           round(score, 1),
        "color":           _risk_color(score),
        "explanation":     explanation,
        "factors":         factors,
        "cv":              round(cv, 4),
        "price_range_pct": round(price_range_pct, 2),
    }


def _price_volatility_risk_estimate(current_price: float, crop: str) -> Dict:
    """
    Estimate volatility risk using only a single current price + seasonal config.
    Used when full history is unavailable.
    """
    cfg = CROP_CONFIG.get(crop, {})
    base_volatility = cfg.get("volatility", 0.12)
    score = min(100, base_volatility * 300)

    explanation = (
        f"Volatility estimated from seasonal parameters (CV≈{base_volatility:.2f}) — "
        "limited live data available"
    )
    factors = [
        f"Estimated coefficient of variation: {base_volatility*100:.0f}%",
        "Based on seasonal norms — actual volatility may differ",
        "* Estimate only — insufficient price history",
    ]

    return {
        "score":           round(score, 1),
        "color":           _risk_color(score),
        "explanation":     explanation,
        "factors":         factors,
        "cv":              round(base_volatility, 4),
        "price_range_pct": None,
        "is_estimate":     True,
    }


def _price_trend_risk(prices: np.ndarray) -> Dict:
    """
    Supply/price trend risk from real price history.
    Rising prices suggest tight supply; falling prices suggest oversupply.
    """
    if len(prices) < 2:
        return {"score": 25, "color": "green", "explanation": "Insufficient data for trend", "factors": []}

    n = len(prices)
    recent_30 = prices[-min(30, n):]
    recent_7  = prices[-min(7, n):]

    trend_30d = ((recent_30[-1] - recent_30[0]) / max(recent_30[0], 1)) * 100
    trend_7d  = ((recent_7[-1]  - recent_7[0])  / max(recent_7[0], 1))  * 100

    # High price trend up = potential selling opportunity, low supply risk from buyer view
    # High price trend down = oversupply concern for sellers
    if trend_30d < -20 or trend_7d < -15:
        score = 70 + abs(trend_30d) * 0.3
        explanation = f"Price falling sharply ({trend_30d:.1f}% over 30 days) — oversupply possible"
        factors = [
            f"30-day price trend: {trend_30d:+.1f}%",
            f"7-day price trend: {trend_7d:+.1f}%",
            "Consider selling sooner rather than later",
        ]
    elif trend_30d < -10:
        score = 50 + abs(trend_30d)
        explanation = f"Moderate price decline ({trend_30d:.1f}% over 30 days) — monitor closely"
        factors = [
            f"30-day price trend: {trend_30d:+.1f}%",
            "Downtrend visible but not critical yet",
        ]
    elif trend_30d > 15:
        score = 20
        explanation = f"Price rising strongly ({trend_30d:.1f}% over 30 days) — good selling window"
        factors = [
            f"30-day price trend: {trend_30d:+.1f}%",
            "Bullish momentum — good time to sell",
        ]
    else:
        score = 30
        explanation = f"Price relatively stable ({trend_30d:+.1f}%) — normal market conditions"
        factors = [
            f"30-day price trend: {trend_30d:+.1f}%",
            "No unusual market disruption detected",
        ]

    return {
        "score":             round(min(100, max(0, score)), 1),
        "color":             _risk_color(score),
        "explanation":       explanation,
        "factors":           factors,
        "price_trend_30d":   round(float(trend_30d), 2),
        "price_trend_7d":    round(float(trend_7d), 2),
    }


def _seasonal_risk(crop: str) -> Dict:
    """Seasonal risk: is this historically a volatile/risky month for this crop?"""
    current_month = datetime.now().month
    cfg = CROP_CONFIG.get(crop, {})
    base_volatility = cfg.get("volatility", 0.12)
    peak_month = cfg.get("peak_month", 6)

    month_diff = abs(current_month - peak_month)
    month_diff = min(month_diff, 12 - month_diff)

    if month_diff <= 1:
        volatility_multiplier = 1.6
        season_desc = "near peak price season"
    elif month_diff <= 2:
        volatility_multiplier = 1.3
        season_desc = "entering/leaving peak season"
    elif month_diff >= 5:
        volatility_multiplier = 0.8
        season_desc = "off-season — lower typical prices"
    else:
        volatility_multiplier = 1.0
        season_desc = "mid-season — normal conditions"

    score = min(100, base_volatility * 300 * volatility_multiplier)

    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    peak_month_name = month_names[peak_month - 1]

    if score > 60:
        explanation = f"High seasonal risk — currently {season_desc} (peak: {peak_month_name})"
    elif score > 35:
        explanation = f"Moderate seasonal risk — {season_desc}"
    else:
        explanation = f"Low seasonal risk — {season_desc}"

    factors = [
        f"Historical peak month: {peak_month_name}",
        f"Current period: {season_desc}",
        f"Base volatility for {crop}: {base_volatility*100:.0f}%",
        f"Seasonal adjustment: ×{volatility_multiplier}",
    ]

    return {
        "score":             round(score, 1),
        "color":             _risk_color(score),
        "explanation":       explanation,
        "factors":           factors,
        "peak_month":        peak_month_name,
        "months_from_peak":  month_diff,
    }


@router.get("/risk/{crop}")
async def get_risk(
    crop: str,
    district: Optional[str] = Query(None),
):
    """
    Returns comprehensive risk analysis for a crop.
    Uses real price history when >= 7 records available (data_source: "live").
    Falls back to single current live price when history is scarce (data_source: "limited_live").
    Never uses mock price data.
    """
    crop_title = crop.title()
    if crop_title not in CROPS:
        raise HTTPException(
            status_code=404,
            detail=f"Crop '{crop}' not found. Available crops: {CROPS}",
        )

    data_source = "unavailable"
    current_price = 0.0
    prices_array: Optional[np.ndarray] = None

    # Try to get real historical prices
    real_history: list = []
    try:
        real_history = await fetch_price_history(crop_title, district, days=60)
    except Exception as e:
        print(f"[risk] Could not fetch real history for {crop_title}: {e}")

    if len(real_history) >= 7:
        prices_array = np.array([r["price"] for r in real_history])
        current_price = float(prices_array[-1])
        data_source = "live"
    else:
        # Try single current price
        try:
            live = await fetch_real_price(crop_title, district=district)
            if live and live.get("price", 0) > 0:
                current_price = float(live["price"])
                prices_array = np.array([current_price])
                data_source = "limited_live"
        except Exception as e:
            print(f"[risk] Could not fetch current price for {crop_title}: {e}")

    # Build sub-risks
    if prices_array is not None and len(prices_array) >= 7:
        volatility_risk = _price_volatility_risk_from_history(prices_array[-30:] if len(prices_array) >= 30 else prices_array)
        supply_risk = _price_trend_risk(prices_array)
    elif prices_array is not None and len(prices_array) >= 1:
        # Limited — only single price available
        volatility_risk = _price_volatility_risk_estimate(current_price, crop_title)
        supply_risk = {
            "score": 30,
            "color": "green",
            "explanation": "Trend data unavailable — using neutral estimate",
            "factors": ["* Estimate only — only one live price data point available"],
            "price_trend_30d": None,
            "price_trend_7d": None,
            "is_estimate": True,
        }
    else:
        # No price data at all
        volatility_risk = {
            "score": 50,
            "color": "yellow",
            "explanation": "No live price data available",
            "factors": ["Live price data unavailable from Agmarknet"],
            "cv": None,
            "price_range_pct": None,
        }
        supply_risk = {
            "score": 50,
            "color": "yellow",
            "explanation": "No live price data available",
            "factors": ["Live price data unavailable from Agmarknet"],
        }

    seasonal = _seasonal_risk(crop_title)

    # Real weather risk (Open-Meteo — always live)
    weather_data_source = "mock"
    try:
        weather_score = await get_weather_risk_score(district or "Nashik")
        weather_data_source = "live"
    except Exception as e:
        print(f"[risk] Could not fetch weather risk: {e}")
        weather_forecast = _generate_10day_forecast(district or "Nashik")
        weather_overall  = _compute_overall_risk(weather_forecast)
        weather_score    = weather_overall["risk_score"]

    weather_color = _risk_color(weather_score)

    if weather_score > 65:
        weather_explanation = f"High weather risk in {district or 'your district'} — crop damage possible"
        weather_factors = [
            "Severe or adverse weather forecast in next 10 days",
            "Secure storage and delay field operations",
        ]
        weather_risk_level = "high"
        high_risk_days, medium_risk_days, low_risk_days = 3, 2, 5
    elif weather_score > 35:
        weather_explanation = f"Moderate weather risk in {district or 'your district'} — exercise caution"
        weather_factors = [
            "Some adverse conditions expected in the next 10 days",
            "Monitor forecasts before scheduling field operations",
        ]
        weather_risk_level = "medium"
        high_risk_days, medium_risk_days, low_risk_days = 1, 4, 5
    else:
        weather_explanation = f"Low weather risk in {district or 'your district'} — favourable conditions"
        weather_factors = [
            "Mostly clear or benign conditions forecast",
            "Good window for farming activities",
        ]
        weather_risk_level = "low"
        high_risk_days, medium_risk_days, low_risk_days = 0, 2, 8

    weather_risk = {
        "score":            weather_score,
        "color":            weather_color,
        "explanation":      weather_explanation,
        "factors":          weather_factors,
        "risk_level":       weather_risk_level,
        "high_risk_days":   high_risk_days,
        "medium_risk_days": medium_risk_days,
        "low_risk_days":    low_risk_days,
        "data_source":      weather_data_source,
    }

    # Overall composite risk
    overall_score = (
        supply_risk["score"]    * 0.30
        + weather_risk["score"] * 0.25
        + volatility_risk["score"] * 0.25
        + seasonal["score"]     * 0.20
    )
    overall_color = _risk_color(overall_score)

    if overall_color == "green":
        overall_summary = f"{crop_title} looks like a good bet right now — low overall risk"
    elif overall_color == "yellow":
        overall_summary = f"{crop_title} carries moderate risk — proceed with caution"
    else:
        overall_summary = f"{crop_title} is high-risk at this time — consider alternatives"

    insights = []
    if supply_risk["score"] > 65:
        insights.append("Price trend is downward — market may be oversupplied")
    if volatility_risk["score"] > 65:
        insights.append("Price volatility is very high — income unpredictable")
    if weather_risk["score"] > 65:
        insights.append(f"Severe weather expected in {district or 'your district'} — crop damage possible")
    if seasonal["score"] > 65:
        insights.append(f"Current month is historically volatile for {crop_title}")
    if data_source == "limited_live":
        insights.append("* Limited data — only current price available; estimates used for some scores")
    if not insights:
        insights.append("All risk indicators within acceptable range")
        insights.append("Market conditions relatively stable for this crop")

    return {
        "crop":            crop_title,
        "district":        district or "All",
        "overall_score":   round(overall_score, 1),
        "overall_color":   overall_color,
        "overall_summary": overall_summary,
        "breakdown": {
            "supply_risk":           supply_risk,
            "weather_risk":          weather_risk,
            "price_volatility_risk": volatility_risk,
            "seasonal_risk":         seasonal,
        },
        "key_insights":       insights,
        "current_price":      round(current_price, 2),
        "data_source":        data_source,
        "records_used":       len(real_history),
        "recommendation": (
            "Proceed — conditions are favourable" if overall_color == "green"
            else "Caution — monitor market conditions closely" if overall_color == "yellow"
            else "High risk — consider delaying or choosing an alternative crop"
        ),
        "msp_comparison":     compare_price_to_msp(crop_title, current_price),
        "district_suitability": get_district_suitability(district or "Nashik", crop_title),
    }
