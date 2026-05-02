"""
GET /api/weather/{district}
Returns real weather data from Open-Meteo API (free, no key needed).
Falls back to deterministic mock data if the API is unavailable.
"""

from fastapi import APIRouter, HTTPException
from typing import List, Dict, Optional
import httpx
import hashlib
from datetime import datetime, timedelta
from data.mock_data import DISTRICTS

router = APIRouter()

# District → (latitude, longitude)
DISTRICT_COORDS: dict = {
    "Nashik":     (20.0059, 73.7898),
    "Pune":       (18.5204, 73.8567),
    "Nagpur":     (21.1458, 79.0882),
    "Solapur":    (17.6805, 75.9064),
    "Aurangabad": (19.8762, 75.3433),
    "Kolhapur":   (16.7050, 74.2433),
    "Satara":     (17.6805, 74.0183),
    "Ahmednagar": (19.0948, 74.7480),
    "Latur":      (18.4088, 76.5604),
    "Jalgaon":    (21.0077, 75.5626),
}

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

# ── Legacy mock constants (kept for fallback) ────────────────────────────────

WEATHER_CONDITIONS = [
    "Clear", "Partly Cloudy", "Cloudy", "Light Rain", "Moderate Rain",
    "Heavy Rain", "Thunderstorm", "Heatwave", "Fog", "Windy",
]

RISK_CONDITIONS = {
    "Heavy Rain":    ("high",   "Flood risk — delay sowing, harvest urgently"),
    "Thunderstorm":  ("high",   "Crop damage likely — secure storage"),
    "Heatwave":      ("high",   "High evapotranspiration — irrigation critical"),
    "Moderate Rain": ("medium", "Good for soil moisture but watch for fungal disease"),
    "Light Rain":    ("low",    "Beneficial light showers — good planting window"),
    "Fog":           ("medium", "Reduced visibility and disease risk in cold-weather crops"),
    "Windy":         ("medium", "Watch for soil erosion and crop lodging"),
    "Cloudy":        ("low",    "Overcast sky — moderate conditions"),
    "Partly Cloudy": ("low",    "Favourable conditions for most crops"),
    "Clear":         ("low",    "Ideal field operations weather"),
}


def _district_hash(district: str) -> int:
    return int(hashlib.md5(district.encode()).hexdigest(), 16) % 10000


def _generate_10day_forecast(district: str) -> List[Dict]:
    """Generate a deterministic 10-day forecast for a district (mock fallback)."""
    base_seed = _district_hash(district)
    today = datetime.now()
    forecast = []

    for i in range(10):
        day_seed = (base_seed + i * 137 + today.month * 31) % len(WEATHER_CONDITIONS)
        condition = WEATHER_CONDITIONS[day_seed]
        risk_level, risk_note = RISK_CONDITIONS[condition]

        month = today.month
        base_temp = 28 + 6 * (abs(month - 7) / 6 - 0.5)
        temp_offset = (base_seed % 8) - 4
        temp_max = round(base_temp + temp_offset + i * 0.2, 1)
        temp_min = round(temp_max - 8 - (day_seed % 4), 1)
        humidity = 40 + (day_seed * 5) % 50

        forecast.append({
            "date":          (today + timedelta(days=i)).strftime("%Y-%m-%d"),
            "day":           i,
            "condition":     condition,
            "temp_max":      temp_max,
            "temp_min":      temp_min,
            "humidity":      humidity,
            "risk_level":    risk_level,
            "risk_note":     risk_note,
            "rainfall_mm":   round((day_seed * 3.7) % 40, 1)
                             if "Rain" in condition or "Thunder" in condition else 0,
            "precipitation_mm": round((day_seed * 3.7) % 40, 1)
                                if "Rain" in condition or "Thunder" in condition else 0.0,
            "risk_score":    75 if risk_level == "high" else 45 if risk_level == "medium" else 15,
        })

    return forecast


def _compute_overall_risk(forecast: List[Dict]) -> Dict:
    """Compute overall weather risk from a 10-day forecast."""
    risk_counts = {"low": 0, "medium": 0, "high": 0}
    for day in forecast:
        risk_counts[day["risk_level"]] += 1

    if risk_counts["high"] >= 3:
        level = "high"
        score = 75 + risk_counts["high"] * 3
        alert = f"Severe weather expected on {risk_counts['high']} days — plan operations carefully"
    elif risk_counts["high"] >= 1 or risk_counts["medium"] >= 4:
        level = "medium"
        score = 40 + risk_counts["medium"] * 4 + risk_counts["high"] * 8
        alert = "Mixed conditions ahead — monitor forecasts before field operations"
    else:
        level = "low"
        score = 10 + risk_counts["medium"] * 5
        alert = "Favourable weather conditions expected — good window for farming activities"

    return {
        "risk_level":       level,
        "risk_score":       min(100, score),
        "alert":            alert,
        "high_risk_days":   risk_counts["high"],
        "medium_risk_days": risk_counts["medium"],
        "low_risk_days":    risk_counts["low"],
    }


# ── WMO weather code helpers ─────────────────────────────────────────────────

def _wmo_to_condition(code: int) -> str:
    if code <= 2:
        return "Clear" if code == 0 else "Partly Cloudy"
    if code == 3:
        return "Cloudy"
    if code in (45, 48):
        return "Fog"
    if 51 <= code <= 67:
        return "Light Rain" if code <= 55 else "Moderate Rain"
    if 71 <= code <= 77:
        return "Cloudy"   # Snow — rare in Maharashtra, map to cloudy
    if 80 <= code <= 82:
        return "Moderate Rain" if code == 80 else "Heavy Rain"
    if code in (85, 86):
        return "Heavy Rain"
    if 95 <= code <= 99:
        return "Thunderstorm"
    return "Partly Cloudy"


def _assess_day_risk(code: int, temp_max: float, precip_mm: float) -> tuple:
    """
    Returns (risk_level, risk_score, condition_str) for one forecast day.
    """
    condition = _wmo_to_condition(code)

    if temp_max > 40 or precip_mm > 50 or code in (85, 86) or 95 <= code <= 99:
        risk_level = "high"
        risk_score = 80
    elif 80 <= code <= 82 or 51 <= code <= 67:
        risk_level = "medium"
        risk_score = 50
    elif code in (45, 48, 3) or (51 <= code <= 55):
        risk_level = "low"
        risk_score = 25
    else:
        risk_level = "low"
        risk_score = 10

    # Override if heatwave or extreme rain
    if temp_max > 40:
        condition = "Heatwave"
        risk_level = "high"
        risk_score = 85
    elif precip_mm > 50:
        condition = "Heavy Rain"
        risk_level = "high"
        risk_score = 82

    return risk_level, risk_score, condition


def _build_forecast_from_open_meteo(data: dict) -> List[Dict]:
    """Parse Open-Meteo daily JSON into our forecast format."""
    daily = data.get("daily", {})
    dates      = daily.get("time", [])
    precips    = daily.get("precipitation_sum", [])
    temp_maxes = daily.get("temperature_2m_max", [])
    codes      = daily.get("weathercode", [])

    forecast = []
    for i, date_str in enumerate(dates[:10]):
        code      = int(codes[i]) if i < len(codes) and codes[i] is not None else 0
        temp_max  = float(temp_maxes[i]) if i < len(temp_maxes) and temp_maxes[i] is not None else 30.0
        precip_mm = float(precips[i]) if i < len(precips) and precips[i] is not None else 0.0

        risk_level, risk_score, condition = _assess_day_risk(code, temp_max, precip_mm)
        _, risk_note = RISK_CONDITIONS.get(condition, ("low", "Normal conditions"))

        forecast.append({
            "date":             date_str,
            "day":              i,
            "condition":        condition,
            "temp_max":         round(temp_max, 1),
            "temp_min":         None,   # Open-Meteo free tier daily doesn't split min nicely here
            "humidity":         None,
            "risk_level":       risk_level,
            "risk_note":        risk_note,
            "rainfall_mm":      round(precip_mm, 1),
            "precipitation_mm": round(precip_mm, 1),
            "risk_score":       risk_score,
            "wmo_code":         code,
        })

    return forecast


def _parse_soil_moisture(api_data: dict) -> dict:
    """Parse hourly soil moisture from Open-Meteo response."""
    hourly = api_data.get("hourly", {})
    sm_values = hourly.get("soil_moisture_0_to_1cm", [])

    # Today's hours: indices 0-23
    today_values = [v for v in sm_values[:24] if v is not None]
    if not today_values:
        return {
            "current": None,
            "level": "unknown",
            "irrigation_needed": False,
            "advice_mr": "माहिती उपलब्ध नाही",
            "advice_en": "Data not available",
        }

    avg_sm = sum(today_values) / len(today_values)

    if avg_sm < 0.1:
        level = "dry"
        irrigation_needed = True
        advice_mr = "आज पाणी द्या — जमीन कोरडी आहे"
        advice_en = "Water today — soil is dry"
    elif avg_sm <= 0.3:
        level = "optimal"
        irrigation_needed = False
        advice_mr = "पाण्याची पातळी योग्य आहे"
        advice_en = "Moisture optimal — no irrigation needed"
    else:
        level = "wet"
        irrigation_needed = False
        advice_mr = "जास्त पाणी — निचरा तपासा"
        advice_en = "Too wet — check drainage"

    return {
        "current": round(avg_sm, 3),
        "level": level,
        "irrigation_needed": irrigation_needed,
        "advice_mr": advice_mr,
        "advice_en": advice_en,
    }


def _parse_rainfall_forecast(api_data: dict) -> dict:
    """Parse daily precipitation sums from Open-Meteo response."""
    daily = api_data.get("daily", {})
    precips = daily.get("precipitation_sum", [])

    next_7 = sum(v for v in precips[:7] if v is not None)
    next_3 = sum(v for v in precips[:3] if v is not None)

    if next_7 < 5:
        risk = "none"
        advice_mr = "पुढील ७ दिवसांत पाऊस नाही — सिंचन नियोजन करा"
        advice_en = "No rain in next 7 days — plan irrigation"
    elif next_7 < 25:
        risk = "light"
        advice_mr = "हलका पाऊस येण्याची शक्यता — सामान्य शेती कामे करता येतील"
        advice_en = "Light rain expected — normal farm operations possible"
    elif next_7 < 75:
        risk = "moderate"
        advice_mr = "पाऊस येणार — शेतात जाण्याचे नियोजन करा"
        advice_en = "Rain coming — plan your field visits carefully"
    else:
        risk = "heavy"
        advice_mr = "जड पाऊस — पीक संरक्षण करा"
        advice_en = "Heavy rain — protect your crops"

    return {
        "next_7_days_mm": round(next_7, 1),
        "next_3_days_mm": round(next_3, 1),
        "risk": risk,
        "advice_mr": advice_mr,
        "advice_en": advice_en,
    }


def _parse_evapotranspiration(api_data: dict) -> dict:
    """Parse ET0 from Open-Meteo daily response."""
    daily = api_data.get("daily", {})
    et_values = daily.get("et0_fao_evapotranspiration", [])

    today_et = float(et_values[0]) if et_values and et_values[0] is not None else 0.0

    advice_mr = f"आज {today_et:.1f}mm पाण्याची गरज आहे (बाष्पोत्सर्जन)"
    advice_en = f"Today's water requirement: {today_et:.1f}mm (evapotranspiration)"

    return {
        "today_mm": round(today_et, 2),
        "advice_mr": advice_mr,
        "advice_en": advice_en,
    }


async def get_weather_data(district: str) -> dict:
    """
    Fetch real weather from Open-Meteo. Falls back to mock on error.
    Returns the full weather response dict.
    """
    district_title = district.title()
    coords = DISTRICT_COORDS.get(district_title)

    if coords:
        lat, lon = coords
        params = {
            "latitude":    lat,
            "longitude":   lon,
            "daily":       "precipitation_sum,temperature_2m_max,temperature_2m_min,weathercode,et0_fao_evapotranspiration",
            "hourly":      "soil_moisture_0_to_1cm,soil_moisture_1_to_3cm",
            "timezone":    "Asia/Kolkata",
            "forecast_days": 10,
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(OPEN_METEO_URL, params=params)
                if resp.status_code == 200:
                    api_data = resp.json()
                    forecast = _build_forecast_from_open_meteo(api_data)
                    if forecast:
                        overall = _compute_overall_risk(forecast)
                        today_weather = forecast[0]
                        conditions_found = [d["condition"] for d in forecast if d["risk_level"] == "high"]

                        soil_info = _parse_soil_moisture(api_data)
                        rainfall_info = _parse_rainfall_forecast(api_data)
                        et_info = _parse_evapotranspiration(api_data)

                        return {
                            "district":            district_title,
                            "state":               "Maharashtra",
                            "today": {
                                "condition":    today_weather["condition"],
                                "temp_max":     today_weather["temp_max"],
                                "temp_min":     today_weather.get("temp_min"),
                                "humidity":     today_weather.get("humidity"),
                                "rainfall_mm":  today_weather["rainfall_mm"],
                            },
                            "overall_risk":         overall,
                            "high_risk_conditions": list(set(conditions_found)),
                            "forecast":             forecast,
                            "advisory":             _farming_advisory(overall["risk_level"], forecast),
                            "soil_moisture":        soil_info,
                            "rainfall_forecast":    rainfall_info,
                            "evapotranspiration":   et_info,
                            "source":               "live",
                            "data_source":          "live",
                        }
        except Exception as e:
            print(f"[weather] Open-Meteo error for {district_title}: {e}")

    # Fallback to mock
    forecast = _generate_10day_forecast(district_title)
    overall = _compute_overall_risk(forecast)
    today_weather = forecast[0]
    conditions_found = [d["condition"] for d in forecast if d["risk_level"] == "high"]

    return {
        "district":            district_title,
        "state":               "Maharashtra",
        "today": {
            "condition":   today_weather["condition"],
            "temp_max":    today_weather["temp_max"],
            "temp_min":    today_weather["temp_min"],
            "humidity":    today_weather["humidity"],
            "rainfall_mm": today_weather["rainfall_mm"],
        },
        "overall_risk":         overall,
        "high_risk_conditions": list(set(conditions_found)),
        "forecast":             forecast,
        "advisory":             _farming_advisory(overall["risk_level"], forecast),
        "soil_moisture":        None,
        "rainfall_forecast":    None,
        "evapotranspiration":   None,
        "source":               "mock",
        "data_source":          "mock",
    }


async def get_weather_risk_score(district: str) -> int:
    """
    Return just the integer overall risk score (0-100) for a district.
    Used by crops.py and risk.py to avoid duplicate weather fetches.
    """
    data = await get_weather_data(district)
    return int(data["overall_risk"]["risk_score"])


@router.get("/weather/{district}")
async def get_weather(district: str):
    """
    Returns real weather risk and 10-day forecast for the given district.
    Data is fetched from Open-Meteo (free); falls back to deterministic mock.
    """
    district_title = district.title()
    return await get_weather_data(district_title)


@router.get("/soil/{district}")
async def get_soil(district: str):
    """
    Returns soil moisture, rainfall forecast, and evapotranspiration for a district.
    Data sourced from Open-Meteo hourly/daily API.
    """
    district_title = district.title()
    data = await get_weather_data(district_title)
    return {
        "district": district_title,
        "soil_moisture": data.get("soil_moisture"),
        "rainfall_forecast": data.get("rainfall_forecast"),
        "evapotranspiration": data.get("evapotranspiration"),
        "data_source": data.get("data_source"),
    }


def _farming_advisory(risk_level: str, forecast: List[Dict]) -> List[str]:
    """Generate farming-specific advisory based on weather outlook."""
    advisories = []

    rain_days  = [d for d in forecast if "Rain" in d["condition"] or "Thunder" in d["condition"]]
    heat_days  = [d for d in forecast if d["condition"] == "Heatwave"]
    clear_days = [d for d in forecast if d["condition"] in ("Clear", "Partly Cloudy")]

    if rain_days:
        advisories.append(
            f"Rain expected on {len(rain_days)} days — avoid pesticide spraying on those dates"
        )
        if any(d.get("rainfall_mm", 0) > 20 for d in rain_days):
            advisories.append("Heavy rainfall likely — ensure field drainage to prevent waterlogging")

    if heat_days:
        advisories.append(
            f"Heatwave on {len(heat_days)} day(s) — increase irrigation frequency, avoid transplanting"
        )

    if clear_days:
        advisories.append(
            f"{len(clear_days)} clear days ahead — good window for harvesting and post-harvest drying"
        )

    if risk_level == "low":
        advisories.append("Overall conditions favourable — ideal period for sowing and crop management")
    elif risk_level == "medium":
        advisories.append("Exercise caution with timing of field operations — check daily forecasts")
    else:
        advisories.append("High weather risk — prioritise urgent harvest and storage operations")

    return advisories
