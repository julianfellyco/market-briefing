"""Fear & Greed Index — crypto (alternative.me) + stock market (VIX-based)."""
import httpx
import yfinance as yf

LABELS = {
    range(0,  26): ("Extreme Fear",  "😱"),
    range(26, 46): ("Fear",          "😨"),
    range(46, 56): ("Neutral",       "😐"),
    range(56, 76): ("Greed",         "😄"),
    range(76, 101):("Extreme Greed", "🤑"),
}


def _label(value: int) -> tuple:
    for r, (text, emoji) in LABELS.items():
        if value in r:
            return text, emoji
    return "Unknown", "❓"


def get_crypto_fear_greed() -> dict:
    """Crypto Fear & Greed Index from alternative.me (free, no key)."""
    try:
        r = httpx.get(
            "https://api.alternative.me/fng/?limit=2",
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()["data"]
        curr = data[0]
        prev = data[1] if len(data) > 1 else curr
        val  = int(curr["value"])
        text, emoji = _label(val)
        return {
            "value":          val,
            "classification": text,
            "emoji":          emoji,
            "prev_value":     int(prev["value"]),
            "timestamp":      curr.get("timestamp"),
        }
    except Exception as e:
        return {"error": str(e)}


def get_stock_fear_greed() -> dict:
    """Stock market Fear & Greed proxy using VIX (CBOE Volatility Index)."""
    try:
        hist = yf.Ticker("^VIX").history(period="2d")
        if len(hist) < 1:
            return {"error": "No VIX data"}
        vix  = hist["Close"].iloc[-1]
        prev = hist["Close"].iloc[-2] if len(hist) >= 2 else vix

        # Invert VIX → fear/greed score (VIX 10=greed, VIX 40=fear)
        score = max(0, min(100, int(100 - (vix - 10) * (100 / 30))))
        text, emoji = _label(score)
        return {
            "vix":            round(vix, 2),
            "prev_vix":       round(prev, 2),
            "score":          score,
            "classification": text,
            "emoji":          emoji,
        }
    except Exception as e:
        return {"error": str(e)}
