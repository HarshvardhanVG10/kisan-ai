# 🌾 KisanAI — Crop Intelligence Platform

A mobile-first crop intelligence platform for Indian farmers, providing real-time mandi prices, MSP comparison, weather risk, and smart crop recommendations — in Marathi and English.

---

## What It Does

| Question | Answer |
|---|---|
| **काय पेरायचं?** (What to grow?) | Season-based crop recommendations with reasoning |
| **कधी विकायचं?** (When to sell?) | Price trends + 30-day forecast |
| **धोका किती?** (What's the risk?) | 🟢🟡🔴 risk score with breakdown |
| **आजचे भाव** (Today's prices?) | Live mandi prices from Agmarknet |

---

## Live Data Sources

| Data | Source | Update Frequency |
|---|---|---|
| Mandi prices (min/max/modal) | [Agmarknet](https://agmarknet.gov.in) via [data.gov.in](https://data.gov.in) | Daily |
| 10-day weather forecast | [Open-Meteo](https://open-meteo.com) | Real-time |
| Soil moisture & rainfall | [Open-Meteo](https://open-meteo.com) | Real-time |
| MSP (Minimum Support Price) | Govt of India — CCEA announcements | Annual |
| District crop suitability | DES Maharashtra agricultural statistics | Static |

---

## Features

- **Live Agmarknet prices** — fetches real mandi data from data.gov.in API
- **MSP Comparison** — shows if current price is above/below government guaranteed MSP for Wheat, Rice, Maize, Soybean, Cotton
- **District Suitability** — tells farmers how suitable their district is for each crop (e.g. Nashik scores 95/100 for Onion)
- **Real weather** — 10-day forecast with soil moisture, rainfall risk, irrigation advice from Open-Meteo
- **Price Forecast** — 30-day price range prediction using Facebook Prophet
- **Risk Scoring** — composite risk (supply + weather + volatility + seasonal)
- **Marathi + English** — full language toggle
- **Voice output** — 🔊 tap to hear advice in Marathi (Web Speech API)
- **Mobile-first UI** — designed for low-end Android phones

---

## Quick Start

### Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- A free API key from [data.gov.in](https://data.gov.in) → My Account → API Key

### Run

```bash
# 1. Clone
git clone https://github.com/HarshvardhanVG10/kisan-ai.git
cd kisan-ai

# 2. Add your API key
cp backend/.env.example backend/.env
# Edit backend/.env → set DATA_GOV_API_KEY=your_key_here

# 3. Start
docker-compose up --build
```

- **App**: http://localhost:3000
- **API docs**: http://localhost:8000/docs

First build takes 3–5 minutes (Prophet/pystan compilation). Subsequent starts are fast.

---

## API Endpoints

| Endpoint | Description |
|---|---|
| `GET /api/crops?district=Nashik` | Live prices for all crops |
| `GET /api/trends/Onion?district=Nashik` | 30-day price trend |
| `GET /api/forecast/Onion?days=30` | Price forecast |
| `GET /api/weather/Nashik` | Weather + soil moisture |
| `GET /api/risk/Onion?district=Nashik` | Risk score + MSP comparison |
| `GET /api/recommend?district=Nashik&season=Kharif` | Crop recommendations |
| `GET /api/msp/Wheat?price=2100` | MSP comparison for a price |
| `GET /api/soil/Nashik` | Soil moisture + rainfall |

---

## Project Structure

```
kisan-ai/
├── backend/
│   ├── data/
│   │   ├── real_prices.py      # Live Agmarknet API (data.gov.in)
│   │   ├── msp_data.py         # MSP values (Govt of India)
│   │   ├── district_data.py    # District suitability scores
│   │   └── mock_data.py        # Seasonal baseline (fallback only)
│   ├── routers/
│   │   ├── crops_list.py       # GET /api/crops
│   │   ├── trends.py           # GET /api/trends
│   │   ├── forecast.py         # GET /api/forecast
│   │   ├── weather.py          # GET /api/weather + /api/soil
│   │   ├── risk.py             # GET /api/risk
│   │   ├── crops.py            # GET /api/recommend
│   │   └── msp.py              # GET /api/msp
│   ├── main.py
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   └── index.html              # Single-page app (Marathi + English)
├── docker-compose.yml
└── README.md
```

---

## Supported Districts (Maharashtra)

Nashik · Pune · Nagpur · Solapur · Aurangabad · Kolhapur · Satara · Ahmednagar · Latur · Jalgaon

## Supported Crops

Onion · Tomato · Potato · Wheat · Rice · Soybean · Cotton · Maize · Garlic · Chilli

---

## Note on Data Availability

Live Agmarknet data depends on the data.gov.in API. If the API is unreachable (e.g. corporate firewall blocking Docker containers), prices will show as unavailable. Weather, MSP, and district suitability work independently of the price API.
