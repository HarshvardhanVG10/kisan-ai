"""
GET /api/trends/{crop}?district=&days=30
Returns 7-day and 30-day price trends using live data only.
Returns HTTP 503 if fewer than 7 real records are available.
Never uses mock data.
"""

from fastapi import APIRouter, Query, HTTPException
from typing import Optional
import numpy as np
import pandas as pd
from data.mock_data import CROPS
from data.real_prices import fetch_price_history

router = APIRouter()


def _build_trend_summary_from_history(
    crop: str,
    district: Optional[str],
    history: list,
    days: int,
) -> dict:
    """
    Build a trend summary dict from real price history records.
    Gaps (weekends / holidays) are forward-filled.
    """
    df = pd.DataFrame(history)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").set_index("date")
    full_range = pd.date_range(start=df.index.min(), end=df.index.max(), freq="D")
    df = df.reindex(full_range).ffill().reset_index()
    df = df.rename(columns={"index": "date"})

    prices = df["price"].values

    # Trim to requested `days` window
    prices_7d  = prices[-min(7, len(prices)):]
    prices_30d = prices[-min(30, len(prices)):]

    current_price  = float(prices[-1])
    price_7d_ago   = float(prices_7d[0])
    price_30d_ago  = float(prices_30d[0])

    trend_7d  = round(((current_price - price_7d_ago)  / max(price_7d_ago, 1))  * 100, 2)
    trend_30d = round(((current_price - price_30d_ago) / max(price_30d_ago, 1)) * 100, 2)

    if trend_30d > 5:
        signal = "BULLISH"
    elif trend_30d < -5:
        signal = "BEARISH"
    else:
        signal = "NEUTRAL"

    # Build price history list for chart (capped at requested days)
    price_history = [
        {
            "date":          row["date"].strftime("%Y-%m-%d"),
            "price":         round(float(row["price"]), 2),
            "markets_count": int(row["markets_count"]) if "markets_count" in row and not pd.isna(row.get("markets_count")) else None,
        }
        for _, row in df.tail(days).iterrows()
    ]

    return {
        "crop":              crop,
        "district":          district or "All",
        "current_price":     round(current_price, 2),
        "price_trend_7d":    trend_7d,
        "price_trend_30d":   trend_30d,
        "signal":            signal,
        "price_history":     price_history,
        "arrival_trend_30d": None,   # Not reliably available from data.gov.in history
        "data_source":       "live",
        "price_source":      "live",
        "records_used":      len(history),
    }


@router.get("/trends/{crop}")
async def get_trends(
    crop: str,
    district: Optional[str] = Query(None),
    days: int = Query(30, ge=7, le=365),
):
    crop_title = crop.title()
    if crop_title not in CROPS:
        raise HTTPException(
            status_code=404,
            detail=f"Crop '{crop}' not found. Available crops: {CROPS}",
        )

    # Fetch real history (extra headroom for 30-day trend calc)
    fetch_days = max(days + 30, 90)
    real_history: list = []
    try:
        real_history = await fetch_price_history(crop_title, district, days=fetch_days)
    except Exception as e:
        print(f"[trends] Could not fetch real history for {crop_title}: {e}")

    if len(real_history) < 7:
        raise HTTPException(
            status_code=503,
            detail={
                "message": (
                    "Live data not available for this crop in this region. "
                    "Try a different district."
                ),
                "message_mr": (
                    "या पिकाची माहिती या जिल्ह्यासाठी उपलब्ध नाही. "
                    "वेगळा जिल्हा निवडा."
                ),
                "data_source":    "unavailable",
                "records_found":  len(real_history),
                "crop":           crop_title,
                "district":       district or "All",
            },
        )

    summary = _build_trend_summary_from_history(crop_title, district, real_history, days)

    trend_30d     = summary["price_trend_30d"]
    signal        = summary["signal"]
    arr_trend_30d = summary.get("arrival_trend_30d")

    if signal == "BULLISH":
        signal_desc = f"Price up {abs(trend_30d):.1f}% over last {days} days — strong buying signal"
    elif signal == "BEARISH":
        signal_desc = f"Price down {abs(trend_30d):.1f}% over last {days} days — consider waiting"
    else:
        signal_desc = f"Price relatively stable (±{abs(trend_30d):.1f}%) over last {days} days"

    if arr_trend_30d is not None:
        if arr_trend_30d < -10:
            arrival_desc = f"Arrivals falling {abs(arr_trend_30d):.1f}% — supply tightening, prices may rise"
        elif arr_trend_30d > 10:
            arrival_desc = f"Arrivals rising {arr_trend_30d:.1f}% — supply increasing, prices may soften"
        else:
            arrival_desc = f"Arrivals stable ({arr_trend_30d:+.1f}%) — no supply shock expected"
    else:
        arrival_desc = "Arrival data not available for this crop"

    summary["signal_description"]  = signal_desc
    summary["arrival_description"] = arrival_desc

    return summary
