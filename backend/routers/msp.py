"""
GET /api/msp/{crop}?district=&price=
Returns MSP comparison for a crop at a given price (per quintal in ₹).
Also returns district suitability score.
"""

from fastapi import APIRouter, Query, HTTPException
from typing import Optional
from data.mock_data import CROPS
from data.msp_data import get_msp, compare_price_to_msp
from data.district_data import get_district_suitability

router = APIRouter()


@router.get("/msp/{crop}")
async def get_msp_info(
    crop: str,
    district: Optional[str] = Query(None, description="Maharashtra district name"),
    price: Optional[float] = Query(None, description="Current market price per quintal in ₹"),
):
    """
    Returns MSP information for a crop and, if a current price is provided,
    compares it against the official MSP. Also returns district suitability.
    """
    crop_title = crop.title()
    if crop_title not in CROPS:
        raise HTTPException(
            status_code=404,
            detail=f"Crop '{crop}' not found. Available crops: {CROPS}",
        )

    msp_info = get_msp(crop_title)
    district_name = (district or "Nashik").title()
    suitability = get_district_suitability(district_name, crop_title)

    if price is not None and price > 0:
        comparison = compare_price_to_msp(crop_title, price)
    elif msp_info:
        comparison = {
            "under_msp": True,
            "msp": msp_info["msp"],
            "year": msp_info["year"],
            "season": msp_info["season"],
            "source": msp_info["source"],
            "note": "Provide ?price= to compare against MSP",
        }
    else:
        comparison = {
            "under_msp": False,
            "note": "This crop is not under MSP scheme (vegetable)",
        }

    return {
        "crop": crop_title,
        "district": district_name,
        "msp_comparison": comparison,
        "district_suitability": suitability,
    }
