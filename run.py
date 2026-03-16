#!/usr/bin/env python3
"""
Daily Market Briefing Agent (FREE version)
==========================================
Data sources:
  - yfinance        → US indices + IDX/IHSG stocks (free, no key)
  - CoinGecko API   → Crypto prices (free, no key)
  - RSS feeds       → News (free, no key)
  - Claude Opus 4.6 → AI summarizer (needs ANTHROPIC_API_KEY)
  - Telegram Bot    → Delivery (free)

Usage:
  python run.py              # Daemon: runs daily at configured time
  python run.py --now        # Run once immediately
  python run.py --setup      # Configure Telegram bot + Gemini key
  python run.py --hour 6     # Daemon at 6 AM WIB
"""

import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import pytz
import schedule
from dotenv import load_dotenv

from sources.stocks import get_us_indices, get_ihsg, get_idx_movers
from sources.crypto import get_crypto_prices, get_global_market_cap, get_top_movers
from sources.news import fetch_news
from sources.forex import get_forex
from sources.commodities import get_commodities
from sources.fear_greed import get_crypto_fear_greed, get_stock_fear_greed
from sources.sectors import get_monthly_snapshot, get_us_sectors, get_idx_sectors
from sources.utils import safe_fetch, get_logger
from summarizer import generate_briefing
from delivery import get_chat_id, send_telegram, send_photo
from charts import generate_chart
from history import save_briefing
from monthly_wrap import run_monthly_wrap
from quarterly_thesis import run_quarterly_thesis, _quarter_key

load_dotenv()

WIB = pytz.timezone("Asia/Jakarta")
log = get_logger(__name__)


# ── Core job ──────────────────────────────────────────────────────────────────

def run_briefing() -> None:
    now = datetime.now(WIB)
    divider = "=" * 60
    print(f"\n{divider}")
    print(f"🌅  Market Briefing  —  {now.strftime('%A, %B %d, %Y  %H:%M WIB')}")
    print(f"{divider}\n")

    # ── Collect data (parallel) ──────────────────────────────────────────────
    print("🔄  Fetching all market data in parallel...", flush=True)
    _fetch_jobs = {
        "us_indices":        (get_us_indices,       {},                              "US indices"),
        "ihsg":              (get_ihsg,              {},                              "IHSG"),
        "idx_movers":        (get_idx_movers,        {"gainers": [], "losers": []},  "IDX movers"),
        "crypto_prices":     (get_crypto_prices,     {},                              "crypto prices"),
        "global_mc":         (get_global_market_cap, {},                              "global market cap"),
        "top_crypto_movers": (get_top_movers,        {},                              "crypto movers"),
        "news":              (fetch_news,            {},                              "news"),
        "forex":             (get_forex,             {},                              "forex"),
        "commodities":       (get_commodities,       {},                              "commodities"),
        "crypto_fear_greed": (get_crypto_fear_greed, {},                             "crypto F&G"),
        "stock_fear_greed":  (get_stock_fear_greed,  {},                             "stock F&G"),
        "monthly_snapshot":  (get_monthly_snapshot,  {},                             "monthly returns"),
        "us_sectors":        (get_us_sectors,         {},                             "US sectors"),
        "idx_sectors":       (get_idx_sectors,        {},                             "IDX sectors"),
    }
    data = {}
    failed = []
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
                failed.append(label)

    if failed:
        print(f"⚠️  Data unavailable: {', '.join(failed)}")
    else:
        print("✓  All sources fetched")

    # ── Generate briefing ───────────────────────────────────────────────────
    print("\n🤖  Generating briefing with Claude...\n")
    try:
        briefing = generate_briefing(data)
    except Exception as e:
        print(f"❌  Briefing error: {e}")
        return

    print(briefing)
    print(f"\n{divider}")

    # ── Save to history ──────────────────────────────────────────────────────
    try:
        date_saved = save_briefing(briefing, data)
        print(f"💾  Saved to history/{date_saved}.json")
    except Exception as e:
        print(f"⚠️  History save failed: {e}")

    # ── Generate chart ───────────────────────────────────────────────────────
    chart_bytes = None
    try:
        print("📊  Generating chart...", end=" ", flush=True)
        chart_bytes = generate_chart()
        print("✓")
    except Exception as e:
        print(f"⚠️  Chart generation failed: {e}")

    # ── Telegram delivery ───────────────────────────────────────────────────
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id   = os.environ.get("TELEGRAM_CHAT_ID")

    if bot_token and chat_id:
        header = (
            f"🌅 *Market Morning Briefing*\n"
            f"_{now.strftime('%A, %B %d, %Y — %H:%M WIB')}_\n\n"
        )
        # Send chart image first
        if chart_bytes:
            caption = f"📊 Market Chart — {now.strftime('%d %b %Y, %H:%M WIB')}"
            ok_photo = send_photo(chart_bytes, caption, bot_token, chat_id)
            print("✅  Chart sent!" if ok_photo else "⚠️  Chart delivery failed, continuing...")

        ok = send_telegram(header + briefing, bot_token, chat_id)
        print("✅  Sent to Telegram!" if ok else "❌  Telegram delivery failed.")
    else:
        print("ℹ️   Telegram not configured — briefing printed above.")
        print("    Run:  python run.py --setup  to configure Telegram.")


# ── Monthly wrap job ──────────────────────────────────────────────────────────

def run_monthly() -> None:
    now = datetime.now(WIB)
    print(f"\n📅  Monthly Sector Wrap — {now.strftime('%B %Y')}")
    print("=" * 60)
    try:
        result = run_monthly_wrap()
        print("\n" + result["wrap"])

        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
        chat_id   = os.environ.get("TELEGRAM_CHAT_ID")
        if bot_token and chat_id:
            header = (
                f"📅 *Monthly Sector Wrap — {now.strftime('%B %Y')}*\n"
                f"_{now.strftime('%d %B %Y, %H:%M WIB')}_\n\n"
            )
            send_telegram(header + result["wrap"], bot_token, chat_id)
            print("✅  Sent to Telegram!")
    except Exception as e:
        print(f"❌  Monthly wrap failed: {e}")


# ── Quarterly thesis job ────────────────────────────────────────────────────────

def run_quarterly() -> None:
    now  = datetime.now(WIB)
    qkey = _quarter_key(now)
    print(f"\n🎯  Quarterly Thesis — {qkey}")
    print("=" * 60)
    try:
        result = run_quarterly_thesis()
        print("\n" + result["thesis"])

        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
        chat_id   = os.environ.get("TELEGRAM_CHAT_ID")
        if bot_token and chat_id:
            header = (
                f"🎯 *Quarterly Big-Theme Thesis — {qkey}*\n"
                f"_{now.strftime('%d %B %Y, %H:%M WIB')}_\n\n"
            )
            send_telegram(header + result["thesis"], bot_token, chat_id)
            print("✅  Sent to Telegram!")
    except Exception as e:
        print(f"❌  Quarterly thesis failed: {e}")


# ── Setup wizard ──────────────────────────────────────────────────────────────

def setup() -> None:
    print("\n⚙️   Market Briefing Setup")
    print("=" * 40)

    # Claude / Anthropic key
    print("\n── Step 1: Anthropic API Key ──")
    print("  1. Go to: https://console.anthropic.com/")
    print("  2. Settings → API Keys → Create Key")
    print("  3. Copy the key (sk-ant-...)")
    claude = input("\nPaste Anthropic API key (or Enter to skip): ").strip()
    if claude:
        _write_env("ANTHROPIC_API_KEY", claude)
        print("✅  Saved ANTHROPIC_API_KEY")

    # Telegram bot
    print("\n── Step 2: Telegram Bot (FREE) ──")
    print("  1. Open Telegram → search @BotFather")
    print("  2. Send: /newbot  and follow the prompts")
    print("  3. Copy the token it gives you")
    token = input("\nPaste bot token (or Enter to skip): ").strip()
    if not token:
        print("Skipping Telegram setup.")
    else:
        print("\n  4. Open a chat with your new bot")
        print("  5. Send any message (e.g. 'hello')")
        input("  Press Enter after sending the message...")

        chat_id = get_chat_id(token)
        if chat_id:
            print(f"✅  Chat ID detected: {chat_id}")
        else:
            chat_id = input("Could not auto-detect. Enter chat ID manually: ").strip()

        if chat_id:
            _write_env("TELEGRAM_BOT_TOKEN", token)
            _write_env("TELEGRAM_CHAT_ID", chat_id)
            print("✅  Saved Telegram config")

            if input("\nSend a test message? (y/n): ").strip().lower() == "y":
                ok = send_telegram(
                    "✅ *Market Briefing Bot* configured!\n"
                    "You'll receive daily market updates every morning. 🌅",
                    token, chat_id,
                )
                print("✅  Test message sent!" if ok else "❌  Test failed. Check token/chat ID.")

    # Schedule time
    hour = input("\nWhat time (24h, WIB) should the briefing arrive? [7]: ").strip() or "7"
    _write_env("BRIEFING_HOUR", hour)
    print(f"✅  Scheduled for {hour}:00 WIB daily.\n")
    print("Now run:  python run.py --now   (to test immediately)")
    print("      or:  python run.py         (to start daemon)")


def _write_env(key: str, value: str) -> None:
    env_path = Path(".env")
    content = env_path.read_text() if env_path.exists() else ""
    lines = content.splitlines()
    updated = False
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            updated = True
            break
    if not updated:
        lines.append(f"{key}={value}")
    env_path.write_text("\n".join(lines) + "\n")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Daily Market Briefing Agent (free)")
    parser.add_argument("--now",       action="store_true", help="Run daily briefing immediately")
    parser.add_argument("--monthly",   action="store_true", help="Run monthly sector wrap now")
    parser.add_argument("--quarterly", action="store_true", help="Run quarterly thesis now")
    parser.add_argument("--setup",     action="store_true", help="Configure API keys + Telegram")
    parser.add_argument("--hour",      type=int, default=int(os.getenv("BRIEFING_HOUR",   "7")))
    parser.add_argument("--minute",    type=int, default=int(os.getenv("BRIEFING_MINUTE", "0")))
    args = parser.parse_args()

    if args.setup:
        setup()
        return

    if args.now:
        run_briefing()
        return

    if args.monthly:
        run_monthly()
        return

    if args.quarterly:
        run_quarterly()
        return

    # ── Daemon mode ────────────────────────────────────────────────────────
    schedule_time = f"{args.hour:02d}:{args.minute:02d}"
    schedule.every().day.at(schedule_time).do(run_briefing)

    # Monthly wrap: 1st of each month at same hour
    schedule.every().day.at(schedule_time).do(_maybe_monthly)
    # Quarterly thesis: 1st of each quarter (Jan, Apr, Jul, Oct) at same hour
    schedule.every().day.at(schedule_time).do(_maybe_quarterly)

    now_local = datetime.now(WIB)
    print(f"📅  Market Briefing Agent started (FREE mode)")
    print(f"    Daily    : {schedule_time} WIB")
    print(f"    Monthly  : 1st of each month at {schedule_time} WIB")
    print(f"    Quarterly: Jan/Apr/Jul/Oct 1 at {schedule_time} WIB")
    print(f"    Now      : {now_local.strftime('%H:%M')} WIB")
    print(f"    Ctrl+C to stop\n")

    while True:
        schedule.run_pending()
        time.sleep(30)


def _maybe_monthly():
    """Run monthly wrap only on the 1st of each month."""
    if datetime.now(WIB).day == 1:
        run_monthly()


def _maybe_quarterly():
    """Run quarterly thesis only on the 1st of Jan, Apr, Jul, Oct."""
    now = datetime.now(WIB)
    if now.day == 1 and now.month in (1, 4, 7, 10):
        run_quarterly()


if __name__ == "__main__":
    main()
