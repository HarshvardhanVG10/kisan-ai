/**
 * KisanAI Price Fetcher - Cloudflare Worker
 * Runs daily via cron trigger, fetches prices from data.gov.in
 * and stores them in Railway PostgreSQL via a webhook endpoint.
 *
 * Cron: 0 1 * * * (runs at 1:00 AM UTC = 6:30 AM IST daily)
 */

const DATA_GOV_API_KEY = "579b464db66ec23bdd0000011300c8f2d5a440d463c2548e38d6c820";
const RESOURCE_ID = "9ef84268-d588-465a-a308-a864a43d0070";
const BASE_URL = `https://api.data.gov.in/resource/${RESOURCE_ID}`;
const RAILWAY_WEBHOOK = "https://kisan-ai-production-aab8.up.railway.app/api/ingest-prices";

const CROP_COMMODITY_MAP = {
  Onion:   ["Onion", "Onions"],
  Tomato:  ["Tomato", "Tomatoes"],
  Potato:  ["Potato", "Potatoes"],
  Wheat:   ["Wheat"],
  Rice:    ["Rice", "Paddy(Dhan)(Common)"],
  Soybean: ["Soyabean", "Soybean"],
  Cotton:  ["Cotton", "Cotton(Lint)"],
  Maize:   ["Maize"],
  Garlic:  ["Garlic"],
  Chilli:  ["Dry Chillies", "Chilli"],
};

async function fetchCropData(commodity) {
  const params = new URLSearchParams({
    "api-key": DATA_GOV_API_KEY,
    format: "json",
    limit: "500",
    "filters[commodity]": commodity,
    "filters[state]": "Maharashtra",
  });

  const resp = await fetch(`${BASE_URL}?${params}`);
  if (!resp.ok) return [];
  const data = await resp.json();
  return data.records || [];
}

function parseDate(str) {
  try {
    const [d, m, y] = str.trim().split("/");
    return new Date(`${y}-${m}-${d}`);
  } catch {
    return new Date(0);
  }
}

function processRecords(records) {
  // Get latest record
  const valid = records.filter(r => r.modal_price && parseFloat(r.modal_price) > 0);
  if (!valid.length) return { current: null, history: [] };

  valid.sort((a, b) => parseDate(b.arrival_date) - parseDate(a.arrival_date));
  const latest = valid[0];

  const current = {
    price: parseFloat(latest.modal_price),
    min_price: parseFloat(latest.min_price || 0),
    max_price: parseFloat(latest.max_price || 0),
    market: latest.market || "",
    district: latest.district || "",
    state: latest.state || "Maharashtra",
    date: latest.arrival_date || "",
    commodity: latest.commodity || "",
    tier: 2,
    source: "cloudflare",
  };

  // Build history: group by date, compute median price
  const dateMap = {};
  for (const r of valid) {
    const raw = r.arrival_date?.trim();
    if (!raw) continue;
    try {
      const dt = parseDate(raw);
      const iso = dt.toISOString().split("T")[0];
      if (!dateMap[iso]) dateMap[iso] = [];
      dateMap[iso].push(parseFloat(r.modal_price));
    } catch {}
  }

  const history = Object.entries(dateMap)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, prices]) => ({
      date,
      price: prices.reduce((a, b) => a + b, 0) / prices.length,
      markets_count: prices.length,
    }));

  return { current, history };
}

async function runFetch() {
  const payload = {};

  for (const [crop, commodities] of Object.entries(CROP_COMMODITY_MAP)) {
    for (const commodity of commodities) {
      try {
        const records = await fetchCropData(commodity);
        if (records.length > 0) {
          payload[crop] = processRecords(records);
          break;
        }
      } catch (e) {
        console.log(`Error fetching ${commodity}: ${e.message}`);
      }
    }
    if (!payload[crop]) {
      payload[crop] = { current: null, history: [] };
    }
  }

  // Send to Railway backend
  const resp = await fetch(RAILWAY_WEBHOOK, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-KisanAI-Secret": "kisanai2025" },
    body: JSON.stringify(payload),
  });

  return { status: resp.status, crops: Object.keys(payload).length };
}

export default {
  // HTTP trigger (for manual testing)
  async fetch(request, env, ctx) {
    if (request.method === "GET") {
      const result = await runFetch();
      return new Response(JSON.stringify(result), {
        headers: { "Content-Type": "application/json" },
      });
    }
    return new Response("KisanAI Price Fetcher", { status: 200 });
  },

  // Cron trigger (runs daily at 1:00 AM UTC = 6:30 AM IST)
  async scheduled(event, env, ctx) {
    ctx.waitUntil(runFetch());
  },
};
