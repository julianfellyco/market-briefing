"""Live forex rates using yfinance (free, no API key)."""
import yfinance as yf

PAIRS = {
    "USD/IDR": "USDIDR=X",
    "EUR/IDR": "EURIDR=X",
    "SGD/IDR": "SGDIDR=X",
    "JPY/IDR": "JPYIDR=X",
    "GBP/IDR": "GBPIDR=X",
}


def _pct(prev, curr):
    return (curr - prev) / prev * 100 if prev else 0.0


def get_forex() -> dict:
    result = {}
    for name, ticker in PAIRS.items():
        try:
            hist = yf.Ticker(ticker).history(period="2d")
            if len(hist) < 1:
                continue
            curr = hist["Close"].iloc[-1]
            prev = hist["Close"].iloc[-2] if len(hist) >= 2 else curr
            result[name] = {
                "rate":       round(curr, 2),
                "change_pct": round(_pct(prev, curr), 2),
            }
        except Exception:
            continue
    return result
