# MSP data - updated annually by Cabinet Committee on Economic Affairs (CCEA)
# Source: Ministry of Agriculture & Farmers Welfare
# Note: Vegetables (Onion, Tomato, Potato, Garlic, Chilli) are NOT under MSP scheme

MSP_DATA = {
    "Wheat":   {"2024-25": 2275, "2025-26": 2425, "season": "Rabi"},
    "Rice":    {"2024-25": 2183, "2025-26": 2369, "season": "Kharif"},
    "Maize":   {"2024-25": 1962, "2025-26": 2225, "season": "Kharif"},
    "Soybean": {"2024-25": 4600, "2025-26": 4950, "season": "Kharif"},
    "Cotton":  {"2024-25": 7020, "2025-26": 7121, "season": "Kharif"},
    # Vegetables not under MSP scheme
    "Onion":   None,
    "Tomato":  None,
    "Potato":  None,
    "Garlic":  None,
    "Chilli":  None,
}

CURRENT_YEAR = "2025-26"

def get_msp(crop: str) -> dict | None:
    """Return MSP info for a crop, or None if not under MSP."""
    data = MSP_DATA.get(crop)
    if not data:
        return None
    msp_value = data.get(CURRENT_YEAR)
    if not msp_value:
        return None
    return {
        "msp": msp_value,
        "year": CURRENT_YEAR,
        "season": data.get("season", ""),
        "source": "Cabinet Committee on Economic Affairs (CCEA)",
        "under_msp": True,
    }

def compare_price_to_msp(crop: str, current_price: float) -> dict | None:
    """Compare current market price to MSP. Returns comparison dict or None."""
    msp_info = get_msp(crop)
    if not msp_info:
        return {"under_msp": False, "note": "This crop is not under MSP scheme (vegetable)"}

    msp = msp_info["msp"]
    diff = current_price - msp
    diff_pct = (diff / msp) * 100

    if current_price >= msp * 1.10:
        status = "good"
        label_mr = f"MSP पेक्षा {abs(diff_pct):.0f}% जास्त ✅"
        label_en = f"{abs(diff_pct):.0f}% above MSP ✅"
        advice_mr = "बाजारभाव चांगला आहे — विकण्यास योग्य वेळ"
        advice_en = "Market price is good — good time to sell"
    elif current_price >= msp:
        status = "ok"
        label_mr = f"MSP च्या वर आहे ✅"
        label_en = f"Above MSP ✅"
        advice_mr = "MSP पेक्षा जास्त भाव — सरकारी हमीपेक्षा चांगला"
        advice_en = "Price above MSP — better than government guarantee"
    elif current_price >= msp * 0.90:
        status = "warning"
        label_mr = f"MSP पेक्षा {abs(diff_pct):.0f}% कमी ⚠️"
        label_en = f"{abs(diff_pct):.0f}% below MSP ⚠️"
        advice_mr = "भाव MSP च्या जवळ — सरकारी खरेदी केंद्र तपासा"
        advice_en = "Price near MSP — check government procurement centers"
    else:
        status = "danger"
        label_mr = f"MSP पेक्षा {abs(diff_pct):.0f}% कमी 🔴"
        label_en = f"{abs(diff_pct):.0f}% below MSP 🔴"
        advice_mr = "भाव MSP पेक्षा खूप कमी — सरकारी खरेदी केंद्रात विका"
        advice_en = "Price well below MSP — sell at government procurement center"

    return {
        "under_msp": True,
        "msp": msp,
        "year": msp_info["year"],
        "season": msp_info["season"],
        "current_price": round(current_price, 2),
        "difference": round(diff, 2),
        "difference_pct": round(diff_pct, 1),
        "status": status,
        "label_mr": label_mr,
        "label_en": label_en,
        "advice_mr": advice_mr,
        "advice_en": advice_en,
        "source": msp_info["source"],
    }
