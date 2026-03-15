# Market Briefing

A free, self-hosted daily market briefing agent with a live web dashboard. Covers US equities, Indonesia's IDX/IHSG, crypto, forex, commodities, and macro news — delivered to Telegram every morning and accessible via a real-time web app.

## Features

| | |
|---|---|
| **Daily briefing** | AI-written morning report via Google Gemini Flash (free tier). Falls back to a template formatter if no API key. |
| **Monthly sector wrap** | US and IDX sector performance review, auto-runs on the 1st of each month. |
| **Quarterly macro thesis** | Big-theme 90-day outlook with Bull / Bear / Base cases, auto-runs each quarter. |
| **Live price grid** | Real-time SSE stream — US indices, crypto, commodities, forex. Flash animation on price changes. |
| **IDX top movers** | Scans 60 IDX tickers in parallel, surfaces top 5 gainers and losers. |
| **Market status** | Detects NYSE (pre-market / open / after-hours) and IDX (S1 / lunch / S2) open/closed state. |
| **Interactive charts** | Candlestick charts via TradingView lightweight-charts, 5D–1Y periods. |
| **Sector heatmap** | US sector ETF 30-day performance heatmap on the Monthly tab. |
| **Telegram delivery** | Sends briefing text + chart PNG every morning. |
| **Briefing history** | All past briefings saved to `history/` as JSON, browsable in the Archive tab. |

## Stack

- **Data** — [yfinance](https://github.com/ranaroussi/yfinance) (stocks, forex, commodities), [CoinGecko API](https://www.coingecko.com/en/api) (crypto), RSS feeds (news), [alternative.me](https://alternative.me/crypto/fear-and-greed-index/) (fear & greed)
- **AI** — Google Gemini 2.5 Flash via direct REST API (no SDK, no cost)
- **Backend** — Flask + Server-Sent Events for live streaming
- **Frontend** — Vanilla JS, [lightweight-charts](https://github.com/tradingview/lightweight-charts)
- **Delivery** — Telegram Bot API via httpx

## Quick Start

```bash
git clone https://github.com/julianfellyco/market-briefing.git
cd market-briefing
pip install -r requirements.txt

cp .env.example .env
# Edit .env — add your GEMINI_API_KEY and optionally TELEGRAM_BOT_TOKEN
```

**Run the dashboard:**
```bash
python webapp.py
# Open http://localhost:8080
```

**Run the daily scheduler (briefings at 07:00 WIB):**
```bash
python run.py
```

**Run a briefing immediately:**
```bash
python run.py --now
```

**Run monthly / quarterly reports on demand:**
```bash
python run.py --monthly
python run.py --quarterly
```

## Configuration

All config lives in `.env`:

| Variable | Default | Description |
|---|---|---|
| `GEMINI_API_KEY` | — | Google AI Studio key — free at [aistudio.google.com](https://aistudio.google.com) |
| `TELEGRAM_BOT_TOKEN` | — | From [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_CHAT_ID` | — | Your chat or channel ID |
| `BRIEFING_HOUR` | `7` | Hour (WIB) to send the daily briefing |
| `BRIEFING_MINUTE` | `0` | Minute to send |

No API key = template-based briefing (still works, just not AI-written).

## Auto-start on macOS (launchd)

Two plist files are installed in `~/Library/LaunchAgents/`:
- `com.marketbriefing.webapp.plist` — keeps the dashboard running
- `com.marketbriefing.runner.plist` — runs the daily scheduler

```bash
# Load (after cloning)
launchctl load ~/Library/LaunchAgents/com.marketbriefing.webapp.plist
launchctl load ~/Library/LaunchAgents/com.marketbriefing.runner.plist

# Restart webapp
launchctl kickstart -k gui/$(id -u)/com.marketbriefing.webapp

# Check status
launchctl list | grep marketbriefing
```

Logs: `logs/webapp.log`, `logs/runner.log`, `logs/app.log`

## Project Layout

```
market-briefing/
├── webapp.py              # Flask app + API endpoints
├── run.py                 # Scheduler + CLI runner
├── summarizer.py          # Gemini briefing generator (falls back to template)
├── charts.py              # matplotlib chart PNG generator
├── delivery.py            # Telegram text + photo delivery
├── history.py             # JSON history persistence
├── monthly_wrap.py        # Monthly sector wrap generator
├── quarterly_thesis.py    # Quarterly macro thesis generator
│
├── sources/
│   ├── stocks.py          # US indices + IHSG + IDX movers (60-ticker universe)
│   ├── crypto.py          # CoinGecko prices, market cap, top movers
│   ├── forex.py           # USD/EUR/SGD/JPY/GBP/AUD/CNY/HKD/CAD vs IDR
│   ├── commodities.py     # Gold, Silver, Oil, Gas, Copper, Corn, Wheat
│   ├── fear_greed.py      # Crypto F&G (alternative.me) + Stock F&G (VIX-based)
│   ├── news.py            # RSS feeds — US, Indonesia, Crypto, Macro
│   ├── sectors.py         # US sector ETFs + IDX sectoral indices (for monthly/quarterly)
│   ├── market_status.py   # NYSE and IDX open/closed detection (pure datetime logic)
│   └── utils.py           # retry-with-backoff, safe_fetch, centralised logging
│
├── templates/
│   └── index.html         # Single-page dashboard (vanilla JS + lightweight-charts)
│
├── history/               # Generated at runtime — daily / monthly / quarterly JSON
├── logs/                  # Generated at runtime — app.log, webapp.log, runner.log
│
├── requirements.txt
├── .env.example
└── README.md
```

## API Endpoints

| Endpoint | Description |
|---|---|
| `GET /` | Dashboard (index.html) |
| `GET /api/status` | App status, last/next run, Gemini/Telegram state |
| `GET /api/health` | Lightweight healthcheck |
| `GET /api/live` | Live price snapshot (cached 15s) |
| `GET /api/prices/stream` | SSE stream — price updates every 10s |
| `GET /api/movers` | IDX top gainers/losers (cached 2 min) |
| `GET /api/market-status` | NYSE + IDX open/closed status |
| `GET /api/chart-data/<ticker>?p=<period>` | OHLC candlestick data |
| `POST /api/run` | Trigger a daily briefing |
| `GET /api/stream` | SSE log stream for briefing progress |
| `GET /api/history` | List of archived briefing dates |
| `GET /api/history/<date>` | Briefing records for a specific date |
| `GET /api/monthly` | List of monthly sector wraps |
| `GET /api/monthly/<month>` | A specific monthly wrap |
| `POST /api/monthly/run` | Generate monthly wrap now |
| `GET /api/quarterly` | List of quarterly theses |
| `GET /api/quarterly/<qkey>` | A specific quarterly thesis |
| `POST /api/quarterly/run` | Generate quarterly thesis now |

## Roadmap

- **Phase 2** — improved data accuracy, retries/logging, tests, dashboard polish
- **Phase 3** — database, user watchlists, multi-channel delivery, public deployment
