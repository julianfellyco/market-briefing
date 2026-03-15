"""Fetch US and IDX stock data using yfinance (free, no API key)."""
from concurrent.futures import ThreadPoolExecutor, as_completed

import yfinance as yf

from sources.utils import get_logger

log = get_logger(__name__)

US_INDICES = {
    "^GSPC": "S&P 500",
    "^IXIC": "NASDAQ",
    "^DJI":  "Dow Jones",
}

# Broader IDX universe — LQ45 + additional blue chips (~60 tickers)
IDX_UNIVERSE = [
    # Financials
    "BBCA.JK", "BBRI.JK", "BMRI.JK", "BNGA.JK", "BBNI.JK", "BTPS.JK", "ARTO.JK", "BRIS.JK",
    # Consumer & Retail
    "UNVR.JK", "ICBP.JK", "INDF.JK", "MYOR.JK", "SIDO.JK", "CLEO.JK", "ACES.JK", "MAPI.JK",
    # Telco & Tech
    "TLKM.JK", "EXCL.JK", "ISAT.JK", "GOTO.JK", "BUKA.JK", "EMTK.JK", "TOWR.JK", "LINK.JK",
    # Energy & Mining
    "BYAN.JK", "ADRO.JK", "PTBA.JK", "ITMG.JK", "INCO.JK", "MDKA.JK", "ANTM.JK", "TINS.JK",
    "MEDC.JK", "PGAS.JK",
    # Infrastructure & Construction
    "JSMR.JK", "WIKA.JK", "WSKT.JK", "PTPP.JK", "ADHI.JK", "PGEO.JK",
    # Property
    "SMRA.JK", "BSDE.JK", "CTRA.JK", "PWON.JK",
    # Auto & Industrial
    "ASII.JK", "INTP.JK", "SMGR.JK",
    # Healthcare & Pharma
    "KLBF.JK", "KAEF.JK",
    # Agri & Plantation
    "LSIP.JK", "AALI.JK", "DSNG.JK",
    # Media
    "SCMA.JK", "MNCN.JK",
]
IDX_UNIVERSE = list(dict.fromkeys(IDX_UNIVERSE))  # deduplicate


def _pct(prev, curr):
    if prev and prev != 0:
        return (curr - prev) / prev * 100
    return 0.0


def _fetch_2d(sym: str):
    """Returns (curr, prev) or (None, None) on failure."""
    try:
        hist = yf.Ticker(sym).history(period="2d", timeout=10)
        if len(hist) < 1:
            return None, None
        curr = float(hist["Close"].iloc[-1])
        prev = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else curr
        return curr, prev
    except Exception as e:
        log.debug(f"{sym}: {e}")
        return None, None


def get_us_indices() -> dict:
    result = {}
    with ThreadPoolExecutor(max_workers=3) as ex:
        futures = {ex.submit(_fetch_2d, t): (t, n) for t, n in US_INDICES.items()}
        for fut in as_completed(futures):
            _, name = futures[fut]
            curr, prev = fut.result()
            result[name] = (
                {"price": round(curr, 2), "change_pct": round(_pct(prev, curr), 2)}
                if curr else {"price": None, "change_pct": None}
            )
    order = list(US_INDICES.values())
    return {k: result[k] for k in order if k in result}


def get_ihsg() -> dict:
    curr, prev = _fetch_2d("^JKSE")
    if curr:
        return {"price": round(curr, 2), "change_pct": round(_pct(prev, curr), 2)}
    return {"price": None, "change_pct": None}


def get_idx_movers() -> dict:
    """Scan broader IDX universe in parallel, return top 5 gainers & losers."""
    gainers, losers = [], []
    with ThreadPoolExecutor(max_workers=12) as ex:
        futures = {ex.submit(_fetch_2d, sym): sym for sym in IDX_UNIVERSE}
        for fut in as_completed(futures):
            sym = futures[fut]
            curr, prev = fut.result()
            if curr is None or prev is None or prev == 0:
                continue
            pct = _pct(prev, curr)
            entry = {
                "ticker":     sym.replace(".JK", ""),
                "price":      round(curr),
                "change_pct": round(pct, 2),
            }
            (gainers if pct >= 0 else losers).append(entry)

    gainers.sort(key=lambda x: x["change_pct"], reverse=True)
    losers.sort(key=lambda x: x["change_pct"])
    return {"gainers": gainers[:5], "losers": losers[:5]}
