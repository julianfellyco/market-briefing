"""
Market Briefing Web App
Run: python webapp.py
Then open: http://localhost:8080
"""

import json
import os
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import schedule

import pytz
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request, stream_with_context

from sources.utils import get_logger

load_dotenv()
log = get_logger(__name__)

app = Flask(__name__)
WIB = pytz.timezone("Asia/Jakarta")

# ── Shared state ──────────────────────────────────────────────────────────────
_state = {
    "running": False,
    "last_run": None,
    "last_briefing": None,
    "last_error": None,
}
_subscribers: list = []
_subs_lock = threading.Lock()

# ── Live price cache ──────────────────────────────────────────────────────────
_live_cache    = {"data": None, "ts": 0}
_LIVE_TTL      = 15   # seconds
_SECTORS_TTL   = 300  # 5 min


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status")
def status():
    hour   = int(os.environ.get("BRIEFING_HOUR",   "7"))
    minute = int(os.environ.get("BRIEFING_MINUTE", "0"))
    now    = datetime.now(WIB)
    if now.hour < hour or (now.hour == hour and now.minute < minute):
        next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    else:
        from datetime import timedelta
        next_run = (now + timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0)

    return jsonify({
        "running":       _state["running"],
        "last_run":      _state["last_run"],
        "last_error":    _state["last_error"],
        "next_run":      next_run.strftime("%A, %b %d — %H:%M WIB"),
        "has_briefing":  _state["last_briefing"] is not None,
        "briefing":      _state["last_briefing"],
        "telegram_ok":   bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID")),
        "gemini_ok":     bool(os.environ.get("GEMINI_API_KEY")),
    })


def _run_briefing():
    """Core briefing logic — called by the scheduler and by /api/run."""
    if _state["running"]:
        return
    _state["running"] = True
    _state["last_error"] = None
    _log("start", "")

    try:
        from sources.stocks import get_us_indices, get_ihsg, get_idx_movers
        from sources.crypto import get_crypto_prices, get_global_market_cap, get_top_movers
        from sources.news import fetch_news
        from summarizer import generate_briefing
        from delivery import send_telegram

        from sources.forex import get_forex
        from sources.commodities import get_commodities
        from sources.fear_greed import get_crypto_fear_greed, get_stock_fear_greed
        from sources.sectors import get_monthly_snapshot, get_us_sectors, get_idx_sectors
        from delivery import send_photo
        from charts import generate_chart
        from history import save_briefing
        from sources.utils import safe_fetch

        _fetch_jobs = {
            "us_indices":        (get_us_indices,        {},                              "📊 US indices"),
            "ihsg":              (get_ihsg,               {},                              "🇮🇩 IHSG"),
            "idx_movers":        (get_idx_movers,         {"gainers":[],"losers":[]},      "📈 IDX movers"),
            "crypto_prices":     (get_crypto_prices,      {},                              "₿ Crypto prices"),
            "global_mc":         (get_global_market_cap,  {},                              "₿ Global market cap"),
            "top_crypto_movers": (get_top_movers,         {},                              "₿ Crypto movers"),
            "news":              (fetch_news,             {},                              "📰 News"),
            "forex":             (get_forex,              {},                              "💱 Forex"),
            "commodities":       (get_commodities,        {},                              "🥇 Commodities"),
            "crypto_fear_greed": (get_crypto_fear_greed,  {},                             "😱 Crypto F&G"),
            "stock_fear_greed":  (get_stock_fear_greed,   {},                             "😱 Stock F&G"),
            "monthly_snapshot":  (get_monthly_snapshot,   {},                             "📅 Monthly returns"),
            "us_sectors":        (get_us_sectors,          {},                             "📊 US sectors"),
            "idx_sectors":       (get_idx_sectors,         {},                             "🇮🇩 IDX sectors"),
        }

        _log("step", "🔄 Fetching all market data in parallel...")
        data = {}
        failed_sources = []
        with ThreadPoolExecutor(max_workers=8) as ex:
            futures = {
                ex.submit(safe_fetch, fn, default=default, label=label): key
                for key, (fn, default, label) in _fetch_jobs.items()
            }
            for future in as_completed(futures):
                key = futures[future]
                result = future.result()
                data[key] = result
                fn, default, label = _fetch_jobs[key]
                if result == default:
                    failed_sources.append(label)

        if failed_sources:
            _log("step", f"⚠️ Unavailable: {', '.join(failed_sources)}")
        else:
            _log("step", "✓ All sources fetched")

        _log("step", "🤖 Generating briefing with Gemini...")
        briefing = generate_briefing(data)
        _state["last_briefing"] = briefing
        _state["last_run"] = datetime.now(WIB).strftime("%A, %b %d — %H:%M WIB")

        try:
            save_briefing(briefing, data)
        except Exception:
            pass

        _log("briefing", briefing)

        bot  = os.environ.get("TELEGRAM_BOT_TOKEN")
        chat = os.environ.get("TELEGRAM_CHAT_ID")
        if bot and chat:
            try:
                chart_bytes = generate_chart()
                now_wib = datetime.now(WIB)
                send_photo(chart_bytes, f"📊 Market Chart — {now_wib.strftime('%d %b %Y, %H:%M WIB')}", bot, chat)
                _log("step", "📊 Chart sent to Telegram.")
            except Exception as e:
                _log("step", f"⚠️ Chart failed: {e}")

            now_wib = datetime.now(WIB)
            header = (
                f"🌅 *Market Morning Briefing*\n"
                f"_{now_wib.strftime('%A, %B %d, %Y — %H:%M WIB')}_\n\n"
            )
            ok = send_telegram(header + briefing, bot, chat)
            _log("step", "✅ Sent to Telegram!" if ok else "❌ Telegram delivery failed.")
        else:
            _log("step", "ℹ️ Telegram not configured.")

    except Exception as e:
        _state["last_error"] = str(e)
        _log("error", str(e))
    finally:
        _state["running"] = False
        _log("done", "")


@app.route("/api/run", methods=["POST"])
def run_now():
    if _state["running"]:
        return jsonify({"error": "Already running"}), 409
    threading.Thread(target=_run_briefing, daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/stream")
def stream():
    """SSE log stream — one queue per client, no message loss between tabs."""
    q = _subscribe()

    def event_stream():
        try:
            while True:
                try:
                    msg = q.get(timeout=30)
                    yield f"data: {json.dumps(msg)}\n\n"
                    if msg["type"] in ("done", "error"):
                        break
                except queue.Empty:
                    yield 'data: {"type":"ping"}\n\n'
        finally:
            _unsubscribe(q)

    return Response(stream_with_context(event_stream()), mimetype="text/event-stream")


WATCH = {
    "S&P 500":   ("^GSPC",    "index"),
    "NASDAQ":    ("^IXIC",    "index"),
    "Dow Jones": ("^DJI",     "index"),
    "IHSG":      ("^JKSE",    "index"),
    "Bitcoin":   ("BTC-USD",  "crypto"),
    "Ethereum":  ("ETH-USD",  "crypto"),
    "Gold":      ("GC=F",     "commodity"),
    "WTI Oil":   ("CL=F",     "commodity"),
    "USD/IDR":   ("USDIDR=X", "forex"),
    "EUR/IDR":   ("EURIDR=X", "forex"),
}


def _fetch_one(name, ticker, category):
    import yfinance as yf
    try:
        hist = yf.Ticker(ticker).history(period="2d", timeout=10)
        if len(hist) < 1:
            return None
        price = float(hist["Close"].iloc[-1])
        prev  = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else price
        pct   = (price - prev) / prev * 100 if prev else 0.0
        return {
            "name":     name,
            "ticker":   ticker,
            "category": category,
            "price":    round(price, 4),
            "change":   round(pct, 2),
        }
    except Exception as e:
        log.debug(f"WATCH {ticker}: {e}")
        return None


def _fetch_all_prices():
    """Fetch all WATCH tickers in parallel. Falls back to stale cache on total failure."""
    results = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        futures = {ex.submit(_fetch_one, n, t, c): n for n, (t, c) in WATCH.items()}
        for future in as_completed(futures):
            r = future.result()
            if r:
                results.append(r)

    # If we got nothing and have stale cache, return stale data
    if not results and _live_cache["data"]:
        log.warning("All WATCH fetches failed; serving stale cache")
        return _live_cache["data"]["items"]

    order = list(WATCH.keys())
    results.sort(key=lambda x: order.index(x["name"]) if x["name"] in order else 99)
    return results


@app.route("/api/live")
def live_prices():
    """Live market snapshot — cached 15 s."""
    now = time.time()
    if _live_cache["data"] and now - _live_cache["ts"] < _LIVE_TTL:
        return jsonify(_live_cache["data"])
    items = _fetch_all_prices()
    data  = {"items": items, "updated": datetime.now(WIB).strftime("%H:%M:%S WIB")}
    _live_cache["data"] = data
    _live_cache["ts"]   = now
    return jsonify(data)


@app.route("/api/prices/stream")
def prices_stream():
    """SSE endpoint — pushes fresh prices every 10 s."""
    def generate():
        last = {}
        while True:
            try:
                items = _fetch_all_prices()
                # Tag changed prices
                for item in items:
                    prev = last.get(item["ticker"])
                    item["up"]   = prev is not None and item["price"] > prev
                    item["down"] = prev is not None and item["price"] < prev
                    last[item["ticker"]] = item["price"]
                payload = {
                    "items":   items,
                    "updated": datetime.now(WIB).strftime("%H:%M:%S WIB"),
                }
                yield f"data: {json.dumps(payload)}\n\n"
            except Exception:
                pass
            time.sleep(10)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/api/chart-data/<path:ticker>")
def chart_data(ticker: str):
    """OHLC history for lightweight-charts. period = ?p=30d (default)."""
    import yfinance as yf
    period = request.args.get("p", "30d")
    try:
        hist = yf.Ticker(ticker).history(period=period)
        if hist.empty:
            return jsonify({"error": "No data"}), 404
        bars = []
        for idx, row in hist.iterrows():
            bars.append({
                "time":  idx.strftime("%Y-%m-%d"),
                "open":  round(float(row["Open"]),  4),
                "high":  round(float(row["High"]),  4),
                "low":   round(float(row["Low"]),   4),
                "close": round(float(row["Close"]), 4),
            })
        return jsonify({"ticker": ticker, "bars": bars})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/monthly")
def get_monthly_list():
    from monthly_wrap import list_monthly
    return jsonify({"months": list_monthly()})


@app.route("/api/monthly/<month_key>")
def get_monthly(month_key: str):
    from monthly_wrap import load_monthly
    d = load_monthly(month_key)
    if not d:
        return jsonify({"error": "Not found"}), 404
    return jsonify(d)


@app.route("/api/monthly/run", methods=["POST"])
def run_monthly_now():
    if _state["running"]:
        return jsonify({"error": "Briefing already running"}), 409

    def _run():
        _state["running"] = True
        _log("start", "")
        try:
            from monthly_wrap import run_monthly_wrap
            _log("step", "📊 Fetching sector data...")
            result = run_monthly_wrap()
            _log("briefing", result["wrap"])
            bot  = os.environ.get("TELEGRAM_BOT_TOKEN")
            chat = os.environ.get("TELEGRAM_CHAT_ID")
            if bot and chat:
                from delivery import send_telegram
                now_wib = datetime.now(WIB)
                header = (
                    f"📅 *Monthly Sector Wrap — {now_wib.strftime('%B %Y')}*\n"
                    f"_{now_wib.strftime('%d %B %Y, %H:%M WIB')}_\n\n"
                )
                ok = send_telegram(header + result["wrap"], bot, chat)
                _log("step", "✅ Sent to Telegram!" if ok else "❌ Telegram failed.")
        except Exception as e:
            _state["last_error"] = str(e)
            _log("error", str(e))
        finally:
            _state["running"] = False
            _log("done", "")

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/quarterly")
def get_quarterly_list():
    from quarterly_thesis import list_quarterly
    return jsonify({"quarters": list_quarterly()})


@app.route("/api/quarterly/<qkey>")
def get_quarterly(qkey: str):
    from quarterly_thesis import load_quarterly
    d = load_quarterly(qkey)
    if not d:
        return jsonify({"error": "Not found"}), 404
    return jsonify(d)


@app.route("/api/quarterly/run", methods=["POST"])
def run_quarterly_now():
    if _state["running"]:
        return jsonify({"error": "Briefing already running"}), 409

    def _run():
        _state["running"] = True
        _log("start", "")
        try:
            from quarterly_thesis import run_quarterly_thesis, _quarter_key
            _log("step", "📈 Fetching macro trends (90d)...")
            result = run_quarterly_thesis()
            _log("briefing", result["thesis"])
            bot  = os.environ.get("TELEGRAM_BOT_TOKEN")
            chat = os.environ.get("TELEGRAM_CHAT_ID")
            if bot and chat:
                from delivery import send_telegram
                now_wib = datetime.now(WIB)
                qkey = _quarter_key(now_wib)
                header = (
                    f"🎯 *Quarterly Thesis — {qkey}*\n"
                    f"_{now_wib.strftime('%d %B %Y, %H:%M WIB')}_\n\n"
                )
                ok = send_telegram(header + result["thesis"], bot, chat)
                _log("step", "✅ Sent to Telegram!" if ok else "❌ Telegram failed.")
        except Exception as e:
            _state["last_error"] = str(e)
            _log("error", str(e))
        finally:
            _state["running"] = False
            _log("done", "")

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/history")
def get_history():
    from history import list_dates
    return jsonify({"dates": list_dates()})


@app.route("/api/history/<date>")
def get_history_date(date: str):
    from history import load_briefing
    records = load_briefing(date)
    if not records:
        return jsonify({"error": "Not found"}), 404
    return jsonify({"date": date, "records": records})


@app.route("/api/settings", methods=["GET"])
def get_settings():
    return jsonify({
        "gemini_key":    "set" if os.environ.get("GEMINI_API_KEY") else "",
        "bot_token":     "set" if os.environ.get("TELEGRAM_BOT_TOKEN") else "",
        "chat_id":       os.environ.get("TELEGRAM_CHAT_ID", ""),
        "briefing_hour": os.environ.get("BRIEFING_HOUR", "7"),
        "briefing_min":  os.environ.get("BRIEFING_MINUTE", "0"),
    })


@app.route("/api/movers")
def get_movers():
    """IDX top gainers/losers — cached 2 min."""
    now = time.time()
    if _live_cache.get("movers") and now - _live_cache.get("movers_ts", 0) < 120:
        return jsonify(_live_cache["movers"])
    try:
        from sources.stocks import get_idx_movers
        data = get_idx_movers()
    except Exception as e:
        log.warning(f"movers fetch failed: {e}")
        data = _live_cache.get("movers") or {"gainers": [], "losers": []}
    _live_cache["movers"]    = data
    _live_cache["movers_ts"] = now
    return jsonify(data)


@app.route("/api/health")
def health():
    """Lightweight healthcheck — returns 200 when the app is up."""
    now = datetime.now(WIB)
    cache_age = round(time.time() - _live_cache["ts"], 1) if _live_cache["ts"] else None
    return jsonify({
        "status":       "ok",
        "time_wib":     now.strftime("%Y-%m-%d %H:%M:%S WIB"),
        "running":      _state["running"],
        "last_run":     _state["last_run"],
        "last_error":   _state["last_error"],
        "cache_age_s":  cache_age,
        "gemini_ok":    bool(os.environ.get("GEMINI_API_KEY")),
        "telegram_ok":  bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID")),
    })


@app.route("/api/market-status")
def market_status():
    from sources.market_status import get_market_status
    return jsonify(get_market_status())


_TICKER_MAP = {
    # Crypto
    "BTC": "BTC-USD", "BITCOIN": "BTC-USD",
    "ETH": "ETH-USD", "ETHEREUM": "ETH-USD",
    "SOL": "SOL-USD", "SOLANA": "SOL-USD",
    "BNB": "BNB-USD", "XRP": "XRP-USD",
    "DOGE": "DOGE-USD", "ADA": "ADA-USD",
    "AVAX": "AVAX-USD", "DOT": "DOT-USD",
    "LINK": "LINK-USD", "UNI": "UNI-USD",
    "MATIC": "MATIC-USD", "ARB": "ARB-USD",
    # Indices
    "SPX": "^GSPC", "SP500": "^GSPC", "S&P": "^GSPC", "S&P500": "^GSPC",
    "NASDAQ": "^IXIC", "NDX": "^IXIC", "COMP": "^IXIC",
    "DJI": "^DJI", "DOW": "^DJI", "DJIA": "^DJI",
    "IHSG": "^JKSE", "IDX": "^JKSE", "JKSE": "^JKSE",
    "NIKKEI": "^N225", "N225": "^N225",
    "HSI": "^HSI", "HANGSENG": "^HSI",
    "VIX": "^VIX",
    # Commodities
    "GOLD": "GC=F", "XAU": "GC=F",
    "SILVER": "SI=F", "XAG": "SI=F",
    "OIL": "CL=F", "WTI": "CL=F", "CRUDE": "CL=F",
    "BRENT": "BZ=F", "NATGAS": "NG=F", "GAS": "NG=F",
    "COPPER": "HG=F",
    # Forex
    "USDIDR": "USDIDR=X", "USD/IDR": "USDIDR=X",
    "EURUSD": "EURUSD=X", "EUR/USD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X", "GBP/USD": "GBPUSD=X",
    "DXY": "DX-Y.NYB", "USDINDEX": "DX-Y.NYB",
}

_analysis_cache: dict = {}
_ANALYSIS_TTL = 300  # 5 min per asset


def _resolve_ticker(asset: str):
    """Return (ticker, display_name) for a given asset string."""
    key = asset.upper().replace(" ", "").replace("-", "")
    if key in _TICKER_MAP:
        return _TICKER_MAP[key], asset.upper()
    # Check original with spaces/dashes
    if asset.upper() in _TICKER_MAP:
        return _TICKER_MAP[asset.upper()], asset.upper()
    return asset.upper(), asset.upper()  # pass through as-is


def _fetch_analysis_data(ticker: str) -> dict:
    import yfinance as yf
    try:
        t = yf.Ticker(ticker)
        hist_1y = t.history(period="1y")
        hist_1mo = t.history(period="1mo")
        hist_7d  = t.history(period="5d")
        if hist_1y.empty:
            return {}

        price    = float(hist_1y["Close"].iloc[-1])
        high_52w = float(hist_1y["High"].max())
        low_52w  = float(hist_1y["Low"].min())

        def pct(old, new):
            return round((new - old) / old * 100, 2) if old else None

        chg_1d  = pct(float(hist_1y["Close"].iloc[-2]), price) if len(hist_1y) >= 2 else None
        chg_7d  = pct(float(hist_7d["Close"].iloc[0]),  price) if len(hist_7d) >= 2 else None
        chg_1mo = pct(float(hist_1mo["Close"].iloc[0]), price) if len(hist_1mo) >= 2 else None
        chg_ytd = pct(float(hist_1y["Close"].iloc[0]),  price)

        vol = float(hist_1y["Volume"].iloc[-1]) if "Volume" in hist_1y.columns else None
        vol_avg = float(hist_1y["Volume"].mean()) if "Volume" in hist_1y.columns else None

        return {
            "price":    round(price, 4),
            "high_52w": round(high_52w, 4),
            "low_52w":  round(low_52w, 4),
            "chg_1d":   chg_1d,
            "chg_7d":   chg_7d,
            "chg_1mo":  chg_1mo,
            "chg_ytd":  chg_ytd,
            "vol":      vol,
            "vol_avg":  vol_avg,
        }
    except Exception as e:
        log.warning(f"analysis data fetch failed for {ticker}: {e}")
        return {}


@app.route("/api/analyze", methods=["POST"])
def analyze_asset():
    body  = request.json or {}
    asset = body.get("asset", "").strip()
    if not asset:
        return jsonify({"error": "Asset required"}), 400

    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return jsonify({"error": "Gemini API key not configured"}), 503

    ticker, display = _resolve_ticker(asset)

    # Cache check
    now = time.time()
    cached = _analysis_cache.get(ticker)
    if cached and now - cached["ts"] < _ANALYSIS_TTL:
        return jsonify(cached["data"])

    mkt = _fetch_analysis_data(ticker)

    # Build market context string
    def fmt(v, pct=False):
        if v is None: return "N/A"
        return f"{v:+.2f}%" if pct else f"{v:,.4g}"

    ctx_lines = [
        f"Asset: {display} ({ticker})",
        f"Current Price: {fmt(mkt.get('price'))}",
        f"1D Change: {fmt(mkt.get('chg_1d'), True)}",
        f"7D Change: {fmt(mkt.get('chg_7d'), True)}",
        f"1M Change: {fmt(mkt.get('chg_1mo'), True)}",
        f"YTD Change: {fmt(mkt.get('chg_ytd'), True)}",
        f"52W High: {fmt(mkt.get('high_52w'))}",
        f"52W Low: {fmt(mkt.get('low_52w'))}",
    ]
    if mkt.get("vol") and mkt.get("vol_avg"):
        vol_ratio = mkt["vol"] / mkt["vol_avg"]
        ctx_lines.append(f"Volume vs Avg: {vol_ratio:.2f}x ({'above' if vol_ratio > 1 else 'below'} average)")

    ctx = "\n".join(ctx_lines)

    prompt = f"""You are a professional hedge fund market analyst.

Analyze the following asset using price action, news sentiment, macro factors, whale activity, and social media narrative.

=== LIVE MARKET DATA ===
{ctx}
=== END DATA ===

Return your analysis as a JSON object with exactly this structure:
{{
  "sentiment": "Bullish" | "Bearish" | "Neutral",
  "confidence": <integer 0-100>,
  "bullish_factors": ["factor 1", "factor 2", "factor 3", ...],
  "bearish_factors": ["factor 1", "factor 2", ...],
  "support_levels": [{{"level": "price or zone", "note": "why it matters"}}, ...],
  "resistance_levels": [{{"level": "price or zone", "note": "why it matters"}}, ...],
  "short_term": "7-day outlook in 2-3 sentences with specific price targets or ranges",
  "long_term": "6-month outlook in 2-3 sentences with macro context"
}}

Be specific with numbers. Use actual price levels, not vague descriptions. Return only valid JSON, no markdown fences.
"""

    try:
        import google.generativeai as genai
        genai.configure(api_key=key)
        model = genai.GenerativeModel("gemini-2.5-flash")
        resp  = model.generate_content(prompt)
        raw   = resp.text.strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw)
    except json.JSONDecodeError:
        result = {"raw": raw}
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    now_wib = datetime.now(WIB)
    out = {
        "asset":     display,
        "ticker":    ticker,
        "market":    mkt,
        "analysis":  result,
        "timestamp": now_wib.strftime("%d %b %Y, %H:%M WIB"),
    }
    _analysis_cache[ticker] = {"data": out, "ts": time.time()}
    return jsonify(out)


@app.route("/api/sectors")
def get_sectors():
    """Sector performance for US, IDX, and Crypto — cached 5 min per period."""
    period = request.args.get("p", "1mo")
    cache_key = f"sectors_{period}"
    now = time.time()
    cached = _live_cache.get(cache_key)
    if cached and now - _live_cache.get(f"{cache_key}_ts", 0) < _SECTORS_TTL:
        return jsonify(cached)
    try:
        from sources.sectors import get_us_sectors, get_idx_sectors, get_crypto_sectors
        results = {}
        with ThreadPoolExecutor(max_workers=3) as ex:
            fs = {
                ex.submit(get_us_sectors,     period): "us",
                ex.submit(get_idx_sectors,    period): "idx",
                ex.submit(get_crypto_sectors, period): "crypto",
            }
            for f in as_completed(fs):
                results[fs[f]] = f.result()
        data = {**results, "period": period, "updated": datetime.now(WIB).strftime("%H:%M:%S WIB")}
        _live_cache[cache_key]            = data
        _live_cache[f"{cache_key}_ts"]    = now
        return jsonify(data)
    except Exception as e:
        log.warning(f"sectors fetch failed: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/settings", methods=["POST"])
def save_settings():
    if not _is_authorized():
        return jsonify({"error": "Unauthorized"}), 401
    body = request.json or {}
    mapping = {
        "gemini_key":    "GEMINI_API_KEY",
        "bot_token":     "TELEGRAM_BOT_TOKEN",
        "chat_id":       "TELEGRAM_CHAT_ID",
        "briefing_hour": "BRIEFING_HOUR",
        "briefing_min":  "BRIEFING_MINUTE",
    }
    for field, env_key in mapping.items():
        val = body.get(field, "").strip()
        if val and val != "set":
            _write_env(env_key, val)
            os.environ[env_key] = val
    load_dotenv(override=True)
    _start_scheduler()   # reschedule if hour/min changed
    return jsonify({"ok": True})


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_authorized() -> bool:
    """Return True if the request carries a valid API_SECRET (or none is configured)."""
    secret = os.environ.get("API_SECRET", "")
    if not secret:
        return True  # dev mode — no secret set
    token = request.headers.get("X-API-Secret") or request.args.get("token", "")
    return token == secret


def _log(msg_type: str, text: str):
    """Broadcast a log message to all connected SSE subscribers."""
    msg = {"type": msg_type, "text": text}
    with _subs_lock:
        dead = []
        for q in _subscribers:
            try:
                q.put_nowait(msg)
            except queue.Full:
                dead.append(q)
        for q in dead:
            try:
                _subscribers.remove(q)
            except ValueError:
                pass


def _subscribe() -> queue.Queue:
    q: queue.Queue = queue.Queue(maxsize=200)
    with _subs_lock:
        _subscribers.append(q)
    return q


def _unsubscribe(q: queue.Queue) -> None:
    with _subs_lock:
        try:
            _subscribers.remove(q)
        except ValueError:
            pass


def _write_env(key: str, value: str):
    env_path = Path(".env")
    content  = env_path.read_text() if env_path.exists() else ""
    lines    = content.splitlines()
    updated  = False
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            updated  = True
            break
    if not updated:
        lines.append(f"{key}={value}")
    env_path.write_text("\n".join(lines) + "\n")


# ── Scheduler ─────────────────────────────────────────────────────────────────

def _start_scheduler():
    """(Re)schedule the daily briefing at the configured WIB time."""
    hour     = int(os.environ.get("BRIEFING_HOUR",   "7"))
    minute   = int(os.environ.get("BRIEFING_MINUTE", "0"))
    time_str = f"{hour:02d}:{minute:02d}"
    schedule.clear("briefing")
    schedule.every().day.at(time_str, "Asia/Jakarta").tag("briefing").do(
        lambda: threading.Thread(target=_run_briefing, daemon=True).start()
    )
    log.info(f"📅 Briefing scheduled daily at {time_str} WIB")


def _scheduler_loop():
    while True:
        schedule.run_pending()
        time.sleep(30)


# ── Startup (runs on import — works with gunicorn and direct run) ──────────────

_start_scheduler()
threading.Thread(target=_scheduler_loop, daemon=True).start()


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print("🌅  Market Briefing Web App")
    print(f"    Open: http://localhost:{port}")
    app.run(debug=False, host="0.0.0.0", port=port, threaded=True)
