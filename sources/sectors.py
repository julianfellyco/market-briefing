"""
Sector performance data.
- US: SPDR sector ETFs (XLK, XLE, XLF, …) via yfinance
- IDX: BEI sectoral indices via yfinance (.JK suffix)
"""
import yfinance as yf
from datetime import datetime, timedelta

US_SECTORS = {
    "Technology":      "XLK",
    "Energy":          "XLE",
    "Financials":      "XLF",
    "Healthcare":      "XLV",
    "Industrials":     "XLI",
    "Consumer Discr.": "XLY",
    "Consumer Stapl.": "XLP",
    "Materials":       "XLB",
    "Real Estate":     "XLRE",
    "Utilities":       "XLU",
    "Communication":   "XLC",
}

IDX_SECTORS = {
    "Energi":         "IDXENERGY.JK",
    "Barang Baku":    "IDXBASIC.JK",
    "Industri":       "IDXINDUST.JK",
    "Barang Konsumsi":"IDXNONCYC.JK",
    "Konsumsi Siklik":"IDXCYCLIC.JK",
    "Kesehatan":      "IDXHEALTH.JK",
    "Keuangan":       "IDXFINANCE.JK",
    "Properti":       "IDXPROPERT.JK",
    "Teknologi":      "IDXTECHNO.JK",
    "Infrastruktur":  "IDXINFRA.JK",
    "Transportasi":   "IDXTRANS.JK",
}


def _pct_change(ticker: str, period: str) -> float | None:
    try:
        hist = yf.Ticker(ticker).history(period=period)
        if len(hist) < 2:
            return None
        start = hist["Close"].iloc[0]
        end   = hist["Close"].iloc[-1]
        return round((end - start) / start * 100, 2)
    except Exception:
        return None


def get_us_sectors(period: str = "1mo") -> dict:
    """Returns {sector_name: {ticker, return_pct}} sorted by return desc."""
    result = {}
    for name, ticker in US_SECTORS.items():
        pct = _pct_change(ticker, period)
        if pct is not None:
            result[name] = {"ticker": ticker, "return_pct": pct}
    return dict(sorted(result.items(), key=lambda x: x[1]["return_pct"], reverse=True))


def get_idx_sectors(period: str = "1mo") -> dict:
    """Returns IDX sectoral index returns sorted by return desc."""
    result = {}
    for name, ticker in IDX_SECTORS.items():
        pct = _pct_change(ticker, period)
        if pct is not None:
            result[name] = {"ticker": ticker, "return_pct": pct}
    return dict(sorted(result.items(), key=lambda x: x[1]["return_pct"], reverse=True))


def get_macro_trends(period: str = "3mo") -> dict:
    """Key macro assets for quarterly thesis — 3-month returns."""
    ASSETS = {
        "S&P 500":    "^GSPC",
        "NASDAQ":     "^IXIC",
        "IHSG":       "^JKSE",
        "Bitcoin":    "BTC-USD",
        "Gold":       "GC=F",
        "WTI Oil":    "CL=F",
        "USD/IDR":    "USDIDR=X",
        "USD Index":  "DX-Y.NYB",
        "US 10Y":     "^TNX",
        "VIX":        "^VIX",
    }
    result = {}
    for name, ticker in ASSETS.items():
        pct = _pct_change(ticker, period)
        if pct is not None:
            result[name] = {"ticker": ticker, "return_pct": pct}
    return result
