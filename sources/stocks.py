"""Fetch US and IDX stock data using yfinance (free, no API key)."""

import yfinance as yf
from datetime import datetime, timedelta


US_INDICES = {
    "^GSPC": "S&P 500",
    "^IXIC": "NASDAQ",
    "^DJI":  "Dow Jones",
}

IDX_TOP = [
    "BBCA.JK", "BBRI.JK", "TLKM.JK", "ASII.JK", "BMRI.JK",
    "BYAN.JK", "UNVR.JK", "GOTO.JK", "MDKA.JK", "INDF.JK",
]


def _pct(prev, curr):
    if prev and prev != 0:
        return (curr - prev) / prev * 100
    return 0.0


def get_us_indices() -> dict:
    result = {}
    for ticker, name in US_INDICES.items():
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="2d")
            if len(hist) < 1:
                result[name] = {"price": None, "change_pct": None}
                continue
            curr = hist["Close"].iloc[-1]
            prev = hist["Close"].iloc[-2] if len(hist) >= 2 else curr
            result[name] = {
                "price": round(curr, 2),
                "change_pct": round(_pct(prev, curr), 2),
            }
        except Exception as e:
            result[name] = {"price": None, "change_pct": None, "error": str(e)}
    return result


def get_ihsg() -> dict:
    try:
        t = yf.Ticker("^JKSE")
        hist = t.history(period="2d")
        if len(hist) < 1:
            return {"price": None, "change_pct": None}
        curr = hist["Close"].iloc[-1]
        prev = hist["Close"].iloc[-2] if len(hist) >= 2 else curr
        return {"price": round(curr, 2), "change_pct": round(_pct(prev, curr), 2)}
    except Exception as e:
        return {"price": None, "change_pct": None, "error": str(e)}


def get_idx_movers() -> dict:
    gainers = []
    losers  = []
    for sym in IDX_TOP:
        try:
            t = yf.Ticker(sym)
            hist = t.history(period="2d")
            if len(hist) < 2:
                continue
            curr = hist["Close"].iloc[-1]
            prev = hist["Close"].iloc[-2]
            pct  = _pct(prev, curr)
            entry = {"ticker": sym.replace(".JK", ""), "price": round(curr), "change_pct": round(pct, 2)}
            (gainers if pct >= 0 else losers).append(entry)
        except Exception:
            continue
    gainers.sort(key=lambda x: x["change_pct"], reverse=True)
    losers.sort(key=lambda x: x["change_pct"])
    return {"gainers": gainers[:5], "losers": losers[:5]}
