"""
GET /api/crops — returns all crops with REAL current prices from data.gov.in.
Only includes crops where live data is available.
Crops with no live data are listed in "unavailable_crops".
Never uses mock prices.
"""

from fastapi import APIRouter, Query
from typing import Optional
from data.mock_data import CROPS, DISTRICTS
from data.real_prices import fetch_all_crops_real

router = APIRouter()


@router.get("/crops")
async def list_crops(district: Optional[str] = Query(None)):
    # Fetch real prices concurrently for all crops
    real = await fetch_all_crops_real(district=district)

    live_crops = []
    unavailable_crops = []

    for crop in CROPS:
        live = real.get(crop)

        if live and live.get("price", 0) > 0 and live.get("source") == "live":
            live_crops.append({
                "crop":       crop,
                "price":      round(live["price"], 2),
                "min_price":  round(live.get("min_price", 0), 2),
                "max_price":  round(live.get("max_price", 0), 2),
                "market":     live.get("market", ""),
                "district":   live.get("district", district or ""),
                "state":      live.get("state", "Maharashtra"),
                "date":       live.get("date", ""),
                "commodity":  live.get("commodity", crop),
                "tier":       live.get("tier", 1),
                "source":     "live",
                # change_pct omitted — we don't have yesterday's real price cached
                "change_pct": None,
            })
        else:
            unavailable_crops.append({
                "crop":   crop,
                "reason": "Live data not available from Agmarknet for this crop/region",
            })

    return {
        "crops":               live_crops,
        "total":               len(live_crops),
        "unavailable_crops":   unavailable_crops,
        "available_districts": DISTRICTS,
        "data_source":         "live",
        "note": (
            "Only crops with live Agmarknet data are shown. "
            "Unavailable crops had no records from data.gov.in."
        ),
    }
