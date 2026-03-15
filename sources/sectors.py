"""
Sector performance data.
- US: SPDR sector ETFs (XLK, XLE, XLF, …) via yfinance
- IDX: BEI sectoral indices via yfinance (.JK suffix)
- Crypto: category-averaged returns (BTC, ETH, L1s, L2s, DeFi, AI, Meme, …)
"""
from concurrent.futures import ThreadPoolExecutor, as_completed

import yfinance as yf

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


# Crypto: (list_of_tickers_to_average, representative_ticker_for_charting)
CRYPTO_SECTORS = {
    "Bitcoin":     (["BTC-USD"],                          "BTC-USD"),
    "Ethereum":    (["ETH-USD"],                          "ETH-USD"),
    "Layer 1s":    (["SOL-USD", "AVAX-USD", "ADA-USD"],   "SOL-USD"),
    "Layer 2s":    (["ARB-USD", "OP-USD", "MATIC-USD"],   "ARB-USD"),
    "DeFi":        (["UNI-USD", "AAVE-USD", "MKR-USD"],   "UNI-USD"),
    "AI / Agents": (["RNDR-USD", "FET-USD", "TAO-USD"],   "RNDR-USD"),
    "Meme":        (["DOGE-USD", "SHIB-USD"],              "DOGE-USD"),
    "Payments":    (["XRP-USD", "LTC-USD"],                "XRP-USD"),
    "Exchange":    (["BNB-USD"],                           "BNB-USD"),
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


def _fetch_parallel(ticker_map: dict, period: str, max_workers: int = 8) -> dict:
    """Fetch pct changes for all tickers in parallel. Returns {ticker: pct}."""
    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_pct_change, ticker, period): ticker for ticker in ticker_map}
        for fut in as_completed(futures):
            ticker = futures[fut]
            results[ticker] = fut.result()
    return results


def get_us_sectors(period: str = "1mo") -> dict:
    """Returns {sector_name: {ticker, return_pct}} sorted by return desc."""
    pcts = _fetch_parallel(US_SECTORS, period)
    result = {}
    for name, ticker in US_SECTORS.items():
        pct = pcts.get(ticker)
        if pct is not None:
            result[name] = {"ticker": ticker, "return_pct": pct}
    return dict(sorted(result.items(), key=lambda x: x[1]["return_pct"], reverse=True))


def get_idx_sectors(period: str = "1mo") -> dict:
    """Returns IDX sectoral index returns sorted by return desc."""
    pcts = _fetch_parallel(IDX_SECTORS, period)
    result = {}
    for name, ticker in IDX_SECTORS.items():
        pct = pcts.get(ticker)
        if pct is not None:
            result[name] = {"ticker": ticker, "return_pct": pct}
    return dict(sorted(result.items(), key=lambda x: x[1]["return_pct"], reverse=True))


def get_crypto_sectors(period: str = "1mo") -> dict:
    """Returns crypto category returns (averaged across representative tokens) sorted desc."""
    # Flatten all tickers for one parallel fetch pass
    all_tickers = {t for tickers, _ in CRYPTO_SECTORS.values() for t in tickers}
    pcts = _fetch_parallel(all_tickers, period)

    result = {}
    for name, (tickers, rep_ticker) in CRYPTO_SECTORS.items():
        valid = [pcts[t] for t in tickers if pcts.get(t) is not None]
        if not valid:
            continue
        avg_pct = round(sum(valid) / len(valid), 2)
        result[name] = {"ticker": rep_ticker, "return_pct": avg_pct}
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
    pcts = _fetch_parallel(ASSETS, period)
    result = {}
    for name, ticker in ASSETS.items():
        pct = pcts.get(ticker)
        if pct is not None:
            result[name] = {"ticker": ticker, "return_pct": pct}
    return result
