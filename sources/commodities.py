"""Commodity prices using yfinance (free, no API key)."""
from concurrent.futures import ThreadPoolExecutor, as_completed

import yfinance as yf

from sources.utils import get_logger

log = get_logger(__name__)

COMMODITIES = {
    "Gold":      ("GC=F", "$/oz"),
    "Silver":    ("SI=F", "$/oz"),
    "WTI Oil":   ("CL=F", "$/bbl"),
    "Brent Oil": ("BZ=F", "$/bbl"),
    "Nat Gas":   ("NG=F", "$/MMBtu"),
    "Copper":    ("HG=F", "$/lb"),
    "Corn":      ("ZC=F", "¢/bu"),
    "Wheat":     ("ZW=F", "¢/bu"),
}


def _pct(prev, curr):
    return (curr - prev) / prev * 100 if prev else 0.0


def _fetch_commodity(ticker: str, unit: str):
    try:
        hist = yf.Ticker(ticker).history(period="2d", timeout=10)
        if len(hist) < 1:
            return None
        curr = float(hist["Close"].iloc[-1])
        prev = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else curr
        return {"price": round(curr, 2), "unit": unit, "change_pct": round(_pct(prev, curr), 2)}
    except Exception as e:
        log.debug(f"Commodity {ticker}: {e}")
        return None


def get_commodities() -> dict:
    result = {}
    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = {ex.submit(_fetch_commodity, t, u): n for n, (t, u) in COMMODITIES.items()}
        for fut in as_completed(futures):
            name = futures[fut]
            data = fut.result()
            if data:
                result[name] = data
    order = list(COMMODITIES.keys())
    return {k: result[k] for k in order if k in result}
