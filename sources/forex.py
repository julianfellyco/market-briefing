"""Live forex rates using yfinance (free, no API key)."""
from concurrent.futures import ThreadPoolExecutor, as_completed

import yfinance as yf

from sources.utils import get_logger

log = get_logger(__name__)

PAIRS = {
    "USD/IDR": "USDIDR=X",
    "EUR/IDR": "EURIDR=X",
    "SGD/IDR": "SGDIDR=X",
    "JPY/IDR": "JPYIDR=X",
    "GBP/IDR": "GBPIDR=X",
    "AUD/IDR": "AUDIDR=X",
    "CNY/IDR": "CNYIDR=X",
    "HKD/IDR": "HKDIDR=X",
    "CAD/IDR": "CADIDR=X",
}


def _pct(prev, curr):
    return (curr - prev) / prev * 100 if prev else 0.0


def _fetch_pair(ticker: str):
    try:
        hist = yf.Ticker(ticker).history(period="2d", timeout=10)
        if len(hist) < 1:
            return None
        curr = float(hist["Close"].iloc[-1])
        prev = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else curr
        return {"rate": round(curr, 2), "change_pct": round(_pct(prev, curr), 2)}
    except Exception as e:
        log.debug(f"Forex {ticker}: {e}")
        return None


def get_forex() -> dict:
    result = {}
    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = {ex.submit(_fetch_pair, t): n for n, t in PAIRS.items()}
        for fut in as_completed(futures):
            name = futures[fut]
            data = fut.result()
            if data:
                result[name] = data
    # Preserve display order
    order = list(PAIRS.keys())
    return {k: result[k] for k in order if k in result}
