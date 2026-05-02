"""
GET /api/forecast/{crop}?days=30
Uses Prophet (if available) or linear regression fallback to forecast prices.
Returns min/max/mean forecast + confidence interval.
Uses live data only — requires >= 14 records; returns 503 otherwise.
Never uses mock data.
"""

from fastapi import APIRouter, Query, HTTPException
from typing import Optional, Dict
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from data.mock_data import CROPS
from data.real_prices import fetch_price_history

router = APIRouter()


def _linear_regression_forecast(prices: np.ndarray, forecast_days: int) -> Dict:
    """Simple linear regression forecast with confidence interval."""
    n = len(prices)
    x = np.arange(n)

    coeffs = np.polyfit(x, prices, 1)
    slope, intercept = coeffs

    fitted = slope * x + intercept
    residuals = prices - fitted
    std_residual = float(np.std(residuals))

    future_x = np.arange(n, n + forecast_days)
    forecast_mean = slope * future_x + intercept

    lower = forecast_mean - 1.28 * std_residual
    upper = forecast_mean + 1.28 * std_residual

    cv = std_residual / max(float(np.mean(prices)), 1)
    confidence = max(0.3, min(0.95, 1.0 - cv * 2))

    return {
        "method":        "linear_regression",
        "forecast_mean": float(np.mean(forecast_mean)),
        "forecast_min":  float(np.mean(lower)),
        "forecast_max":  float(np.mean(upper)),
        "confidence":    round(confidence, 2),
        "trend_slope":   round(float(slope), 4),
        "daily_forecasts": [
            {
                "day":         i + 1,
                "date":        (datetime.now() + timedelta(days=i + 1)).strftime("%Y-%m-%d"),
                "price_mean":  round(float(forecast_mean[i]), 2),
                "price_lower": round(float(lower[i]), 2),
                "price_upper": round(float(upper[i]), 2),
            }
            for i in range(forecast_days)
        ],
    }


def _prophet_forecast(df: pd.DataFrame, forecast_days: int) -> Dict:
    """Forecast using Facebook Prophet."""
    from prophet import Prophet  # type: ignore

    prophet_df = df[["date", "price"]].rename(columns={"date": "ds", "price": "y"})

    model = Prophet(
        yearly_seasonality=True,
        weekly_seasonality=False,
        daily_seasonality=False,
        seasonality_mode="multiplicative",
        interval_width=0.80,
        changepoint_prior_scale=0.05,
    )
    model.fit(prophet_df)

    future = model.make_future_dataframe(periods=forecast_days)
    forecast = model.predict(future)
    future_forecast = forecast.tail(forecast_days)

    forecast_mean = float(future_forecast["yhat"].mean())
    forecast_min  = float(future_forecast["yhat_lower"].mean())
    forecast_max  = float(future_forecast["yhat_upper"].mean())

    interval_ratio = (forecast_max - forecast_min) / max(forecast_mean, 1)
    confidence = max(0.4, min(0.95, 1.0 - interval_ratio * 0.5))

    return {
        "method":        "prophet",
        "forecast_mean": round(forecast_mean, 2),
        "forecast_min":  round(forecast_min, 2),
        "forecast_max":  round(forecast_max, 2),
        "confidence":    round(confidence, 2),
        "trend_slope":   round(
            float(future_forecast["trend"].iloc[-1] - future_forecast["trend"].iloc[0]) / forecast_days,
            4,
        ),
        "daily_forecasts": [
            {
                "day":         i + 1,
                "date":        row["ds"].strftime("%Y-%m-%d"),
                "price_mean":  round(float(row["yhat"]), 2),
                "price_lower": round(float(row["yhat_lower"]), 2),
                "price_upper": round(float(row["yhat_upper"]), 2),
            }
            for i, (_, row) in enumerate(future_forecast.iterrows())
        ],
    }


def _build_df_from_history(history: list) -> pd.DataFrame:
    """
    Convert real price history list to a DataFrame with a continuous daily index.
    Gaps (weekends / holidays) are forward-filled.
    """
    df = pd.DataFrame(history)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").set_index("date")

    full_range = pd.date_range(start=df.index.min(), end=df.index.max(), freq="D")
    df = df.reindex(full_range).ffill()
    df.index.name = "date"
    df = df.reset_index()
    return df


@router.get("/forecast/{crop}")
async def get_forecast(
    crop: str,
    days: int = Query(30, ge=7, le=90),
    district: Optional[str] = Query(None),
):
    """
    Forecast crop prices for the next `days` days using live data.
    Requires >= 14 real historical records; returns 503 otherwise.
    Uses Prophet if available, else falls back to linear regression.
    """
    crop_title = crop.title()
    if crop_title not in CROPS:
        raise HTTPException(
            status_code=404,
            detail=f"Crop '{crop}' not found. Available crops: {CROPS}",
        )

    # Fetch real history (up to 180 days for good model training)
    real_history: list = []
    try:
        real_history = await fetch_price_history(crop_title, district, days=180)
    except Exception as e:
        print(f"[forecast] Could not fetch real history for {crop_title}: {e}")

    if len(real_history) < 14:
        raise HTTPException(
            status_code=503,
            detail={
                "message":    "Insufficient historical data for forecast.",
                "message_mr": "या पिकाचा अंदाज उपलब्ध नाही — पुरेशी माहिती नाही.",
                "data_source":    "unavailable",
                "records_found":  len(real_history),
                "crop":           crop_title,
                "district":       district or "All",
            },
        )

    df = _build_df_from_history(real_history)
    prices = df["price"].values

    # Try Prophet first, fall back to linear regression
    try:
        result = _prophet_forecast(df, forecast_days=days)
    except Exception:
        result = _linear_regression_forecast(prices, forecast_days=days)

    current_price = float(prices[-1])
    expected_change_pct = ((result["forecast_mean"] - current_price) / max(current_price, 1)) * 100

    result["crop"]                 = crop_title
    result["district"]             = district or "All"
    result["current_price"]        = round(current_price, 2)
    result["forecast_days"]        = days
    result["expected_change_pct"]  = round(expected_change_pct, 2)
    result["data_source"]          = "live"
    result["history_records_used"] = len(real_history)
    result["summary"] = (
        f"Expected price range ₹{result['forecast_min']:.0f} – ₹{result['forecast_max']:.0f} "
        f"over next {days} days (mean ₹{result['forecast_mean']:.0f}). "
        f"{'Prices expected to rise' if expected_change_pct > 3 else 'Prices expected to fall' if expected_change_pct < -3 else 'Prices expected to stay stable'} "
        f"({expected_change_pct:+.1f}% from current ₹{current_price:.0f})."
    )

    return result
