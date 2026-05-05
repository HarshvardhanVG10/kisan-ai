"""
Fetches real mandi prices from data.gov.in Agmarknet API.
Resource: Daily prices of various commodities across Indian markets.
Live data only — no mock fallback for prices.
"""

import os
import statistics
import httpx
import asyncio
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("DATA_GOV_API_KEY", "")
RESOURCE_ID = "9ef84268-d588-465a-a308-a864a43d0070"
BASE_URL = f"https://api.data.gov.in/resource/{RESOURCE_ID}"

# Map our app crop names → Agmarknet commodity names (multiple spellings exist)
CROP_COMMODITY_MAP = {
    "Onion":   ["Onion", "Onions"],
    "Tomato":  ["Tomato", "Tomatoes"],
    "Potato":  ["Potato", "Potatoes"],
    "Wheat":   ["Wheat"],
    "Rice":    ["Rice", "Paddy(Dhan)(Common)"],
    "Soybean": ["Soyabean", "Soybean"],
    "Cotton":  ["Cotton", "Cotton(Lint)", "Cotton Seed"],
    "Maize":   ["Maize"],
    "Garlic":  ["Garlic"],
    "Chilli":  ["Dry Chillies", "Chilli", "Green Chilli"],
}

# Cache to avoid hammering the API on every request
_cache: dict = {}
_cache_time: dict = {}
CACHE_TTL_SECONDS = 3600       # 1 hour for current price
HISTORY_CACHE_TTL = 21600      # 6 hours for historical data


def _parse_date(r: dict) -> datetime:
    """Parse arrival_date field from an API record."""
    try:
        return datetime.strptime(r.get("arrival_date", "01/01/2000").strip(), "%d/%m/%Y")
    except Exception:
        return datetime.min


async def fetch_real_price(crop: str, district: Optional[str] = None) -> Optional[dict]:
    """
    Fetch latest modal price for a crop from data.gov.in.
    Uses 3-tier broadening search:
      Tier 1: commodity + district filter (limit=10)
      Tier 2: commodity + state=Maharashtra filter (limit=20)
      Tier 3: commodity only, all-India (limit=20)

    Returns dict with: price, min_price, max_price, market, date, tier, source="live"
    or None if unavailable.
    """
    cache_key = f"{crop}:{district}"
    now = datetime.now().timestamp()

    if cache_key in _cache and (now - _cache_time.get(cache_key, 0)) < CACHE_TTL_SECONDS:
        return _cache[cache_key]

    commodities = CROP_COMMODITY_MAP.get(crop, [crop])

    for commodity in commodities:
        result = await _fetch_with_tiers(commodity, district)
        if result:
            _cache[cache_key] = result
            _cache_time[cache_key] = now
            return result

    return None


async def _fetch_with_tiers(commodity: str, district: Optional[str]) -> Optional[dict]:
    """Try 3 tiers of broadening geographic filters to find any live record."""
    tiers = []

    # Tier 1: district + commodity
    if district:
        tiers.append((1, {
            "api-key": API_KEY,
            "format": "json",
            "limit": "10",
            "filters[commodity]": commodity,
            "filters[district]": district,
        }))

    # Tier 2: Maharashtra state + commodity
    tiers.append((2, {
        "api-key": API_KEY,
        "format": "json",
        "limit": "20",
        "filters[commodity]": commodity,
        "filters[state]": "Maharashtra",
    }))

    # Tier 3: all India + commodity
    tiers.append((3, {
        "api-key": API_KEY,
        "format": "json",
        "limit": "20",
        "filters[commodity]": commodity,
    }))

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            for tier_num, params in tiers:
                try:
                    resp = await client.get(BASE_URL, params=params)
                    if resp.status_code != 200:
                        print(f"[real_prices] Tier {tier_num} HTTP {resp.status_code} for {commodity}: {resp.text[:200]}")
                        continue

                    records = resp.json().get("records", [])
                    valid = [
                        r for r in records
                        if r.get("modal_price") and _safe_float(r["modal_price"]) > 0
                    ]
                    if not valid:
                        continue

                    # Pick most recent record
                    valid.sort(key=_parse_date, reverse=True)
                    r = valid[0]

                    return {
                        "price":     _safe_float(r.get("modal_price", 0)),
                        "min_price": _safe_float(r.get("min_price", 0)),
                        "max_price": _safe_float(r.get("max_price", 0)),
                        "market":    r.get("market", ""),
                        "district":  r.get("district", district or ""),
                        "state":     r.get("state", "Maharashtra"),
                        "date":      r.get("arrival_date", ""),
                        "commodity": r.get("commodity", commodity),
                        "tier":      tier_num,
                        "source":    "live",
                    }
                except Exception as e:
                    print(f"[real_prices] Tier {tier_num} error for {commodity}: {type(e).__name__}: {e}")
                    continue

    except Exception as e:
        print(f"[real_prices] Client error for {commodity}: {e}")

    return None


def _safe_float(val) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


async def fetch_all_crops_real(district: Optional[str] = None) -> dict:
    """Fetch latest prices for all 10 crops concurrently."""
    crops = list(CROP_COMMODITY_MAP.keys())
    tasks = [fetch_real_price(crop, district) for crop in crops]
    results = await asyncio.gather(*tasks)
    return {crop: result for crop, result in zip(crops, results)}


# ---------------------------------------------------------------------------
# Historical price fetch
# ---------------------------------------------------------------------------

async def fetch_price_history(
    crop: str,
    district: Optional[str] = None,
    days: int = 60,
) -> list:
    """
    Fetch historical modal prices for a crop from data.gov.in.

    Strategy:
    - Call API with commodity + state=Maharashtra + limit=500 (no date filter).
    - Parse all records, group by arrival_date.
    - For each date take the median modal_price across all markets.
    - Sort dates ascending, return last `days` entries as:
        [{"date": "YYYY-MM-DD", "price": float, "markets_count": int, "arrivals": int|None}]
    - Return [] only if fewer than 7 unique dates found.
    - Results cached for 6 hours.
    """
    cache_key = f"hist:{crop}:{district}:{days}"
    now = datetime.now().timestamp()

    if cache_key in _cache and (now - _cache_time.get(cache_key, 0)) < HISTORY_CACHE_TTL:
        return _cache[cache_key]

    commodities = CROP_COMMODITY_MAP.get(crop, [crop])

    best_result: list = []
    for commodity in commodities:
        result = await _try_fetch_history(commodity, days)
        if len(result) > len(best_result):
            best_result = result
        if len(best_result) >= 7:
            break  # Good enough — stop trying other spellings

    # Cache result (including empty, to avoid repeated hammering)
    _cache[cache_key] = best_result
    _cache_time[cache_key] = now
    return best_result


async def _try_fetch_history(commodity: str, days: int) -> list:
    """
    Fetch up to 500 records for the commodity from Maharashtra,
    group by date, compute median price per date, return last `days` dates.
    """
    params = {
        "api-key": API_KEY,
        "format": "json",
        "limit": "500",
        "filters[commodity]": commodity,
        "filters[state]": "Maharashtra",
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(BASE_URL, params=params)
            if resp.status_code != 200:
                return []

            records = resp.json().get("records", [])

            if not records:
                # Retry without state filter (all-India) to get any data
                all_india_params = {
                    "api-key": API_KEY,
                    "format": "json",
                    "limit": "500",
                    "filters[commodity]": commodity,
                }
                resp2 = await client.get(BASE_URL, params=all_india_params)
                if resp2.status_code == 200:
                    records = resp2.json().get("records", [])

            if not records:
                return []

            # Group by date: collect prices and arrivals per date
            date_prices: dict[str, list] = {}
            date_arrivals: dict[str, list] = {}

            for r in records:
                raw_date = r.get("arrival_date", "").strip()
                raw_price = r.get("modal_price", "")
                if not raw_date or not raw_price:
                    continue
                try:
                    price = float(raw_price)
                    if price <= 0:
                        continue
                    dt = datetime.strptime(raw_date, "%d/%m/%Y")
                    iso = dt.strftime("%Y-%m-%d")
                    date_prices.setdefault(iso, []).append(price)

                    # Collect arrivals if present
                    raw_arrivals = r.get("arrivals_in_qtl") or r.get("arrivals", "")
                    if raw_arrivals:
                        try:
                            arr_val = float(str(raw_arrivals).replace(",", ""))
                            if arr_val >= 0:
                                date_arrivals.setdefault(iso, []).append(arr_val)
                        except (ValueError, TypeError):
                            pass
                except Exception:
                    continue

            if len(date_prices) < 7:
                return []  # Not enough unique dates

            # Build result: median price per date
            history = []
            for iso_date, prices in sorted(date_prices.items()):
                median_price = statistics.median(prices)
                entry = {
                    "date": iso_date,
                    "price": round(median_price, 2),
                    "markets_count": len(prices),
                }
                # Include median arrivals if available for this date
                if iso_date in date_arrivals and date_arrivals[iso_date]:
                    entry["arrivals"] = round(statistics.median(date_arrivals[iso_date]))
                history.append(entry)

            # Return last `days` entries (ascending)
            return history[-days:]

    except Exception as e:
        print(f"[real_prices] Error fetching history for {commodity}: {type(e).__name__}: {e}")
        return []


async def fetch_all_history(district: Optional[str] = None, days: int = 60) -> dict:
    """Fetch price history for all 10 crops concurrently."""
    crops = list(CROP_COMMODITY_MAP.keys())
    tasks = [fetch_price_history(crop, district, days) for crop in crops]
    results = await asyncio.gather(*tasks)
    return {crop: result for crop, result in zip(crops, results)}
