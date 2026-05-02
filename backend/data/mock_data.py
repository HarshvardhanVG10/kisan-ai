"""
Mock data generator for Indian crop price and arrival data.
Generates 365 days of realistic historical data using seasonal sine-wave patterns + noise.
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# Seed for reproducibility
np.random.seed(42)

CROPS = ["Onion", "Tomato", "Potato", "Wheat", "Rice", "Soybean", "Cotton", "Maize", "Garlic", "Chilli"]

DISTRICTS = ["Nashik", "Pune", "Nagpur", "Solapur", "Aurangabad", "Kolhapur", "Satara", "Ahmednagar", "Latur", "Jalgaon"]

STATES = {
    "Nashik": "Maharashtra",
    "Pune": "Maharashtra",
    "Nagpur": "Maharashtra",
    "Solapur": "Maharashtra",
    "Aurangabad": "Maharashtra",
    "Kolhapur": "Maharashtra",
    "Satara": "Maharashtra",
    "Ahmednagar": "Maharashtra",
    "Latur": "Maharashtra",
    "Jalgaon": "Maharashtra",
}

# Crop configuration: base_price, amplitude, phase_offset (month of peak, 1-12), volatility, trend
CROP_CONFIG = {
    "Onion": {
        "base_price": 1800,       # Rs per quintal
        "amplitude": 900,          # seasonal swing
        "peak_month": 5,           # May-June peak
        "volatility": 0.18,        # std dev as fraction
        "trend": 0.0003,           # daily upward drift
        "base_arrivals": 4500,     # quintals/day
        "arrival_amplitude": 2000,
        "arrival_peak_month": 11,  # Nov-Dec arrivals high (harvest)
    },
    "Tomato": {
        "base_price": 1500,
        "amplitude": 1200,
        "peak_month": 4,
        "volatility": 0.28,        # Very volatile
        "trend": 0.0002,
        "base_arrivals": 6000,
        "arrival_amplitude": 3000,
        "arrival_peak_month": 12,
    },
    "Potato": {
        "base_price": 1200,
        "amplitude": 400,
        "peak_month": 9,
        "volatility": 0.12,
        "trend": 0.0001,
        "base_arrivals": 5000,
        "arrival_amplitude": 2500,
        "arrival_peak_month": 3,
    },
    "Wheat": {
        "base_price": 2200,
        "amplitude": 300,
        "peak_month": 2,           # Feb high, crash in March-April harvest
        "volatility": 0.07,
        "trend": 0.0002,
        "base_arrivals": 8000,
        "arrival_amplitude": 5000,
        "arrival_peak_month": 4,   # Harvest surge in April
    },
    "Rice": {
        "base_price": 2800,
        "amplitude": 250,
        "peak_month": 7,           # Monsoon bump
        "volatility": 0.06,
        "trend": 0.0002,
        "base_arrivals": 9000,
        "arrival_amplitude": 2000,
        "arrival_peak_month": 11,
    },
    "Soybean": {
        "base_price": 4500,
        "amplitude": 600,
        "peak_month": 8,
        "volatility": 0.10,
        "trend": 0.0003,
        "base_arrivals": 3500,
        "arrival_amplitude": 1500,
        "arrival_peak_month": 10,
    },
    "Cotton": {
        "base_price": 6000,
        "amplitude": 800,
        "peak_month": 11,
        "volatility": 0.09,
        "trend": 0.0002,
        "base_arrivals": 2500,
        "arrival_amplitude": 1200,
        "arrival_peak_month": 12,
    },
    "Maize": {
        "base_price": 1800,
        "amplitude": 350,
        "peak_month": 8,
        "volatility": 0.11,
        "trend": 0.0001,
        "base_arrivals": 5500,
        "arrival_amplitude": 2500,
        "arrival_peak_month": 10,
    },
    "Garlic": {
        "base_price": 8000,
        "amplitude": 3000,
        "peak_month": 9,
        "volatility": 0.22,
        "trend": 0.0004,
        "base_arrivals": 1200,
        "arrival_amplitude": 600,
        "arrival_peak_month": 3,
    },
    "Chilli": {
        "base_price": 9000,
        "amplitude": 4000,
        "peak_month": 5,
        "volatility": 0.20,
        "trend": 0.0003,
        "base_arrivals": 1800,
        "arrival_amplitude": 900,
        "arrival_peak_month": 2,
    },
}


def _seasonal_component(day_of_year: np.ndarray, peak_month: int, amplitude: float) -> np.ndarray:
    """Generate a sine-wave seasonal component peaking at the given month."""
    peak_doy = (peak_month - 1) * 30 + 15  # approximate day of year for peak month
    phase = 2 * np.pi * (day_of_year - peak_doy) / 365
    return amplitude * np.sin(phase)


def generate_crop_data(
    crop: str,
    days: int = 365,
    district: Optional[str] = None,
    end_date: Optional[datetime] = None,
) -> pd.DataFrame:
    """
    Generate realistic historical price and arrival data for a given crop.

    Returns a DataFrame with columns:
        date, crop, district, state, price, arrivals, day_of_year
    """
    if crop not in CROP_CONFIG:
        raise ValueError(f"Unknown crop: {crop}. Available: {list(CROP_CONFIG.keys())}")

    cfg = CROP_CONFIG[crop]
    if end_date is None:
        end_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    dates = [end_date - timedelta(days=i) for i in range(days - 1, -1, -1)]
    day_indices = np.arange(days)
    day_of_year = np.array([d.timetuple().tm_yday for d in dates], dtype=float)

    # --- Price generation ---
    # Trend component
    trend = cfg["base_price"] * cfg["trend"] * day_indices
    # Seasonal component
    seasonal = _seasonal_component(day_of_year, cfg["peak_month"], cfg["amplitude"])
    # Noise (proportional to base price)
    noise = np.random.normal(0, cfg["base_price"] * cfg["volatility"], days)
    # Short-term autocorrelated shock (momentum effect)
    shock = np.zeros(days)
    for i in range(1, days):
        shock[i] = 0.7 * shock[i - 1] + 0.3 * np.random.normal(0, cfg["base_price"] * 0.05)

    prices = cfg["base_price"] + trend + seasonal + noise + shock
    prices = np.clip(prices, cfg["base_price"] * 0.3, cfg["base_price"] * 3.5)

    # --- Arrivals generation ---
    arr_trend = cfg["base_arrivals"] * 0.0001 * day_indices
    arr_seasonal = _seasonal_component(day_of_year, cfg["arrival_peak_month"], cfg["arrival_amplitude"])
    arr_noise = np.random.normal(0, cfg["base_arrivals"] * 0.12, days)
    arrivals = cfg["base_arrivals"] + arr_trend + arr_seasonal + arr_noise
    arrivals = np.clip(arrivals, cfg["base_arrivals"] * 0.2, cfg["base_arrivals"] * 2.5)

    # Apply district-specific multiplier (hash-based to be deterministic)
    if district:
        dist_seed = sum(ord(c) for c in district) % 100
        price_mult = 0.92 + (dist_seed / 100) * 0.20   # 0.92 – 1.12
        arr_mult = 0.85 + (dist_seed / 100) * 0.30      # 0.85 – 1.15
        prices = prices * price_mult
        arrivals = arrivals * arr_mult

    df = pd.DataFrame({
        "date": dates,
        "crop": crop,
        "district": district or "All",
        "state": STATES.get(district, "Maharashtra"),
        "price": np.round(prices, 2),
        "arrivals": np.round(arrivals).astype(int),
        "day_of_year": day_of_year.astype(int),
    })

    return df


def get_all_crops_latest(district: Optional[str] = None) -> List[Dict]:
    """Return the latest price snapshot for all crops."""
    result = []
    for crop in CROPS:
        df = generate_crop_data(crop, days=7, district=district)
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        change_pct = ((latest["price"] - prev["price"]) / prev["price"]) * 100
        result.append({
            "crop": crop,
            "price": float(latest["price"]),
            "arrivals": int(latest["arrivals"]),
            "change_pct": round(float(change_pct), 2),
            "district": district or "All",
            "date": latest["date"].strftime("%Y-%m-%d"),
        })
    return result


def get_price_trend_summary(crop: str, district: Optional[str] = None, days: int = 30) -> Dict:
    """Calculate 7-day and 30-day price and arrival trends for a crop."""
    df = generate_crop_data(crop, days=max(days, 35), district=district)
    recent = df.tail(days)

    # 7-day stats
    last7 = df.tail(7)
    first7_price = last7["price"].iloc[0]
    last7_price = last7["price"].iloc[-1]
    trend_7d = ((last7_price - first7_price) / first7_price) * 100

    # 30-day stats
    first_price = recent["price"].iloc[0]
    last_price = recent["price"].iloc[-1]
    trend_30d = ((last_price - first_price) / first_price) * 100

    # Arrival trends
    arr_first7 = last7["arrivals"].iloc[0]
    arr_last7 = last7["arrivals"].iloc[-1]
    arr_trend_7d = ((arr_last7 - arr_first7) / arr_first7) * 100

    arr_first = recent["arrivals"].iloc[0]
    arr_last = recent["arrivals"].iloc[-1]
    arr_trend_30d = ((arr_last - arr_first) / arr_first) * 100

    signal = "BULLISH" if trend_30d > 5 else ("BEARISH" if trend_30d < -5 else "NEUTRAL")

    return {
        "crop": crop,
        "district": district or "All",
        "price_trend_7d": round(float(trend_7d), 2),
        "price_trend_30d": round(float(trend_30d), 2),
        "arrival_trend_7d": round(float(arr_trend_7d), 2),
        "arrival_trend_30d": round(float(arr_trend_30d), 2),
        "current_price": round(float(last_price), 2),
        "avg_price_30d": round(float(recent["price"].mean()), 2),
        "min_price_30d": round(float(recent["price"].min()), 2),
        "max_price_30d": round(float(recent["price"].max()), 2),
        "current_arrivals": int(arr_last),
        "signal": signal,
        "history": [
            {
                "date": row["date"].strftime("%Y-%m-%d"),
                "price": float(row["price"]),
                "arrivals": int(row["arrivals"]),
            }
            for _, row in recent.iterrows()
        ],
    }
