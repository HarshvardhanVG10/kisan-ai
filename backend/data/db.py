"""
Database connection and price storage for KisanAI.
Uses asyncpg for async PostgreSQL access.
"""

import os
import asyncpg
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL", "")

# Convert Railway internal URL to standard asyncpg format
def _get_db_url():
    url = DATABASE_URL
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgres://", 1)
    return url


async def get_conn():
    return await asyncpg.connect(_get_db_url())


async def init_db():
    """Create tables if they don't exist."""
    conn = await get_conn()
    try:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS crop_prices (
                id SERIAL PRIMARY KEY,
                crop VARCHAR(50) NOT NULL,
                district VARCHAR(50),
                price FLOAT,
                min_price FLOAT,
                max_price FLOAT,
                market VARCHAR(100),
                state VARCHAR(50),
                arrival_date VARCHAR(20),
                commodity VARCHAR(100),
                tier INTEGER,
                fetched_at TIMESTAMP DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS price_history (
                id SERIAL PRIMARY KEY,
                crop VARCHAR(50) NOT NULL,
                date VARCHAR(20) NOT NULL,
                price FLOAT NOT NULL,
                markets_count INTEGER,
                arrivals FLOAT,
                fetched_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(crop, date)
            );

            CREATE INDEX IF NOT EXISTS idx_crop_prices_crop ON crop_prices(crop);
            CREATE INDEX IF NOT EXISTS idx_crop_prices_fetched ON crop_prices(fetched_at DESC);
            CREATE INDEX IF NOT EXISTS idx_price_history_crop ON price_history(crop, date);
        """)
        print("[db] Tables initialized.")
    finally:
        await conn.close()


async def save_current_price(crop: str, data: dict):
    """Upsert latest price for a crop."""
    if not data:
        return
    conn = await get_conn()
    try:
        await conn.execute("""
            INSERT INTO crop_prices (crop, district, price, min_price, max_price, market, state, arrival_date, commodity, tier)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        """,
            crop,
            data.get("district", ""),
            data.get("price", 0),
            data.get("min_price", 0),
            data.get("max_price", 0),
            data.get("market", ""),
            data.get("state", ""),
            data.get("date", ""),
            data.get("commodity", crop),
            data.get("tier", 0),
        )
    finally:
        await conn.close()


async def save_price_history(crop: str, history: list):
    """Upsert price history for a crop."""
    if not history:
        return
    conn = await get_conn()
    try:
        for entry in history:
            await conn.execute("""
                INSERT INTO price_history (crop, date, price, markets_count, arrivals)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (crop, date) DO UPDATE
                SET price = EXCLUDED.price,
                    markets_count = EXCLUDED.markets_count,
                    arrivals = EXCLUDED.arrivals,
                    fetched_at = NOW()
            """,
                crop,
                entry.get("date", ""),
                entry.get("price", 0),
                entry.get("markets_count", 0),
                entry.get("arrivals"),
            )
    finally:
        await conn.close()


async def get_latest_price(crop: str, district: str = None) -> dict | None:
    """Get most recent price for a crop from DB."""
    conn = await get_conn()
    try:
        row = await conn.fetchrow("""
            SELECT * FROM crop_prices
            WHERE crop = $1
            ORDER BY fetched_at DESC
            LIMIT 1
        """, crop)
        if not row:
            return None
        return {
            "price": row["price"],
            "min_price": row["min_price"],
            "max_price": row["max_price"],
            "market": row["market"],
            "district": row["district"],
            "state": row["state"],
            "date": row["arrival_date"],
            "commodity": row["commodity"],
            "tier": row["tier"],
            "source": "db_cache",
        }
    finally:
        await conn.close()


async def get_price_history_from_db(crop: str, days: int = 60) -> list:
    """Get price history for a crop from DB."""
    conn = await get_conn()
    try:
        rows = await conn.fetch("""
            SELECT date, price, markets_count, arrivals
            FROM price_history
            WHERE crop = $1
            ORDER BY date ASC
            LIMIT $2
        """, crop, days)
        return [dict(r) for r in rows]
    finally:
        await conn.close()
