"""Commodity prices using yfinance (free, no API key)."""
import yfinance as yf

COMMODITIES = {
    "Gold":       ("GC=F",  "$/oz"),
    "Silver":     ("SI=F",  "$/oz"),
    "WTI Oil":    ("CL=F",  "$/bbl"),
    "Brent Oil":  ("BZ=F",  "$/bbl"),
    "Nat Gas":    ("NG=F",  "$/MMBtu"),
    "Palm Oil":   ("FCPO=F","MYR/t"),
}


def _pct(prev, curr):
    return (curr - prev) / prev * 100 if prev else 0.0


def get_commodities() -> dict:
    result = {}
    for name, (ticker, unit) in COMMODITIES.items():
        try:
            hist = yf.Ticker(ticker).history(period="2d")
            if len(hist) < 1:
                continue
            curr = hist["Close"].iloc[-1]
            prev = hist["Close"].iloc[-2] if len(hist) >= 2 else curr
            result[name] = {
                "price":      round(curr, 2),
                "unit":       unit,
                "change_pct": round(_pct(prev, curr), 2),
            }
        except Exception:
            continue
    return result
