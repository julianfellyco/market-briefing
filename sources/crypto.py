"""Fetch crypto data from CoinGecko public API (free, no API key)."""

import httpx

BASE = "https://api.coingecko.com/api/v3"
HEADERS = {"accept": "application/json"}
TIMEOUT = 15


def get_crypto_prices() -> dict:
    """BTC, ETH prices + 24h change + market cap."""
    try:
        r = httpx.get(
            f"{BASE}/simple/price",
            params={
                "ids": "bitcoin,ethereum",
                "vs_currencies": "usd",
                "include_market_cap": "true",
                "include_24hr_change": "true",
            },
            headers=HEADERS,
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()

        def extract(coin_id):
            d = data.get(coin_id, {})
            return {
                "price": d.get("usd"),
                "change_24h": round(d.get("usd_24h_change", 0), 2),
                "market_cap": d.get("usd_market_cap"),
            }

        return {"bitcoin": extract("bitcoin"), "ethereum": extract("ethereum")}
    except Exception as e:
        return {"error": str(e)}


def get_global_market_cap() -> dict:
    try:
        r = httpx.get(f"{BASE}/global", headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        d = r.json().get("data", {})
        return {
            "total_market_cap_usd": d.get("total_market_cap", {}).get("usd"),
            "market_cap_change_24h": round(d.get("market_cap_change_percentage_24h_usd", 0), 2),
        }
    except Exception as e:
        return {"error": str(e)}


def get_top_movers() -> dict:
    """Top gainers and losers from the top-100 coins by market cap."""
    try:
        r = httpx.get(
            f"{BASE}/coins/markets",
            params={
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": 100,
                "page": 1,
                "price_change_percentage": "24h",
            },
            headers=HEADERS,
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        coins = r.json()

        def fmt(c):
            return {
                "symbol": c.get("symbol", "").upper(),
                "name": c.get("name"),
                "price": c.get("current_price"),
                "change_24h": round(c.get("price_change_percentage_24h") or 0, 2),
            }

        ranked = sorted(coins, key=lambda c: c.get("price_change_percentage_24h") or 0)
        return {
            "gainers": [fmt(c) for c in reversed(ranked[-3:])],
            "losers":  [fmt(c) for c in ranked[:3]],
        }
    except Exception as e:
        return {"error": str(e)}
