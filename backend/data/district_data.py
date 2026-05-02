# District-level crop suitability scores (0-100) based on
# DES crop production statistics and known agro-climatic zones

DISTRICT_CROP_SUITABILITY = {
    "Nashik": {
        "Onion": 95, "Tomato": 80, "Potato": 70, "Wheat": 60, "Rice": 40,
        "Soybean": 65, "Cotton": 55, "Maize": 60, "Garlic": 85, "Chilli": 75,
        "notes": "Famous for Onion (Lasalgaon APMC), Grapes, Tomato"
    },
    "Pune": {
        "Onion": 70, "Tomato": 75, "Potato": 80, "Wheat": 65, "Rice": 50,
        "Soybean": 70, "Cotton": 45, "Maize": 65, "Garlic": 65, "Chilli": 60,
        "notes": "Mixed farming, good for vegetables"
    },
    "Nagpur": {
        "Onion": 50, "Tomato": 60, "Potato": 55, "Wheat": 70, "Rice": 65,
        "Soybean": 80, "Cotton": 90, "Maize": 75, "Garlic": 45, "Chilli": 70,
        "notes": "Famous for Orange, Cotton belt of Vidarbha"
    },
    "Solapur": {
        "Onion": 90, "Tomato": 65, "Potato": 60, "Wheat": 75, "Rice": 35,
        "Soybean": 70, "Cotton": 75, "Maize": 55, "Garlic": 80, "Chilli": 85,
        "notes": "Major Onion and Pomegranate region"
    },
    "Aurangabad": {
        "Onion": 75, "Tomato": 65, "Potato": 55, "Wheat": 70, "Rice": 45,
        "Soybean": 85, "Cotton": 80, "Maize": 70, "Garlic": 60, "Chilli": 75,
        "notes": "Marathwada - Soybean, Cotton, Grape"
    },
    "Kolhapur": {
        "Onion": 60, "Tomato": 80, "Potato": 85, "Wheat": 55, "Rice": 80,
        "Soybean": 60, "Cotton": 40, "Maize": 70, "Garlic": 55, "Chilli": 65,
        "notes": "Sugarcane belt, good rainfall, Rice and vegetables"
    },
    "Satara": {
        "Onion": 75, "Tomato": 75, "Potato": 80, "Wheat": 65, "Rice": 65,
        "Soybean": 65, "Cotton": 50, "Maize": 70, "Garlic": 70, "Chilli": 65,
        "notes": "Strawberry, Potato, mixed vegetables"
    },
    "Ahmednagar": {
        "Onion": 90, "Tomato": 70, "Potato": 65, "Wheat": 70, "Rice": 40,
        "Soybean": 75, "Cotton": 70, "Maize": 65, "Garlic": 75, "Chilli": 70,
        "notes": "Second largest Onion district after Nashik"
    },
    "Latur": {
        "Onion": 70, "Tomato": 60, "Potato": 50, "Wheat": 75, "Rice": 50,
        "Soybean": 90, "Cotton": 75, "Maize": 70, "Garlic": 55, "Chilli": 75,
        "notes": "Soybean capital of Maharashtra"
    },
    "Jalgaon": {
        "Onion": 65, "Tomato": 65, "Potato": 55, "Wheat": 75, "Rice": 55,
        "Soybean": 70, "Cotton": 85, "Maize": 75, "Garlic": 60, "Chilli": 70,
        "notes": "Famous for Banana, Cotton"
    },
}

def get_district_suitability(district: str, crop: str) -> dict:
    """Get crop suitability score for a district."""
    district_data = DISTRICT_CROP_SUITABILITY.get(district, {})
    score = district_data.get(crop, 50)
    notes = district_data.get("notes", "")

    if score >= 80:
        level = "excellent"
        label_mr = "उत्कृष्ट — हा जिल्हा या पिकासाठी प्रसिद्ध आहे"
        label_en = "Excellent — this district is known for this crop"
    elif score >= 65:
        level = "good"
        label_mr = "चांगले — या जिल्ह्यात हे पीक चांगले येते"
        label_en = "Good — this crop grows well in this district"
    elif score >= 45:
        level = "moderate"
        label_mr = "मध्यम — योग्य व्यवस्थापनाने शक्य"
        label_en = "Moderate — possible with proper management"
    else:
        level = "poor"
        label_mr = "कमी — या जिल्ह्यात हे पीक फारसे होत नाही"
        label_en = "Low — this crop is not common in this district"

    return {
        "score": score,
        "level": level,
        "label_mr": label_mr,
        "label_en": label_en,
        "district_notes": notes,
    }
