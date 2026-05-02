# KisanAI — Crop Intelligence Platform

A full-stack agricultural intelligence platform that provides Indian farmers and agri-traders with real-time crop price trends, AI-powered price forecasts, weather risk analysis, and smart crop recommendations.

---

## What It Does

| Feature | Description |
|---|---|
| **Price Trends** | 7-day and 30-day historical price & arrival trends for 10 major Indian crops with Bull/Bear signals |
| **Price Forecast** | 30-day price forecast using Facebook Prophet (with linear regression fallback) |
| **Weather Risk** | 10-day weather risk analysis per district with farming advisories |
| **Risk Analysis** | Composite risk score (green/yellow/red) with breakdown: supply, weather, volatility, seasonal |
| **Crop Recommendations** | Top 3 crops to grow + crops to avoid, per district and season (Kharif/Rabi/Zaid) |
| **Price Snapshot** | Live price table for all 10 crops with daily change % |

---

## Crops Covered

Onion, Tomato, Potato, Wheat, Rice, Soybean, Cotton, Maize, Garlic, Chilli

## Districts Supported

Nashik, Pune, Nagpur, Solapur, Aurangabad, Kolhapur, Satara, Ahmednagar, Latur, Jalgaon (Maharashtra)

---

## How to Run

### Prerequisites
- [Docker](https://www.docker.com/get-started) and [Docker Compose](https://docs.docker.com/compose/) installed

### Start the platform

```bash
cd App2
docker-compose up --build
```

- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Docs (Swagger)**: http://localhost:8000/docs

> First build takes 3–5 minutes (Prophet/pystan compilation). Subsequent starts are fast.

### Stop the platform

```bash
docker-compose down
```

---

## Running Without Docker (Development)

### Backend

```bash
cd App2/backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Frontend

Open `App2/frontend/index.html` directly in a browser, or serve via any static server:

```bash
cd App2/frontend
python -m http.server 3000
```

Then open http://localhost:3000

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/crops` | List all crops with current price snapshot |
| `GET` | `/api/trends/{crop}` | Price & arrival trends. Query: `?district=Nashik&days=30` |
| `GET` | `/api/forecast/{crop}` | Price forecast. Query: `?days=30&district=Nashik` |
| `GET` | `/api/weather/{district}` | Weather risk & 10-day forecast |
| `GET` | `/api/recommend` | Crop recommendations. Query: `?district=Nashik&season=Kharif` |
| `GET` | `/api/risk/{crop}` | Risk analysis. Query: `?district=Nashik` |
| `GET` | `/docs` | Interactive Swagger API documentation |
| `GET` | `/health` | Health check |

### Example Requests

```bash
# Get all crops
curl http://localhost:8000/api/crops

# Get Onion price trends for Nashik (30 days)
curl "http://localhost:8000/api/trends/Onion?district=Nashik&days=30"

# Get 30-day price forecast for Tomato
curl "http://localhost:8000/api/forecast/Tomato?days=30&district=Pune"

# Get weather risk for Nagpur
curl http://localhost:8000/api/weather/Nagpur

# Get Kharif crop recommendations for Solapur
curl "http://localhost:8000/api/recommend?district=Solapur&season=Kharif"

# Get risk analysis for Wheat in Ahmednagar
curl "http://localhost:8000/api/risk/Wheat?district=Ahmednagar"
```

---

## Project Structure

```
App2/
├── docker-compose.yml
├── README.md
│
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py                  # FastAPI app, CORS, router registration
│   ├── data/
│   │   ├── __init__.py
│   │   └── mock_data.py         # Realistic mock data generator
│   └── routers/
│       ├── __init__.py
│       ├── crops_list.py        # GET /api/crops
│       ├── trends.py            # GET /api/trends/{crop}
│       ├── forecast.py          # GET /api/forecast/{crop}
│       ├── weather.py           # GET /api/weather/{district}
│       ├── crops.py             # GET /api/recommend
│       └── risk.py              # GET /api/risk/{crop}
│
└── frontend/
    └── index.html               # Single-page app (Tailwind CDN + Chart.js CDN)
```

---

## Technical Notes

- **Mock Data**: All price and arrival data is synthetically generated using sine-wave seasonal patterns + autocorrelated noise. Data is seeded for reproducibility.
- **Forecasting**: Uses Facebook Prophet for time-series forecasting. Falls back to linear regression if Prophet is unavailable.
- **Weather**: Deterministically generated from district name hash — same district always produces the same weather pattern.
- **Risk Scoring**: Composite of supply risk (arrival trend), weather risk, price volatility (coefficient of variation), and seasonal risk (proximity to historical peak month).

---

## Disclaimer

All data is mock/simulated for demonstration purposes. Do not use for real trading or farming decisions without consulting current APMC market data and local agricultural extension officers.
