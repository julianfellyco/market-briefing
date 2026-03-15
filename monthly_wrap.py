"""
Monthly sector/industry wrap generator.
Runs on the first trading day of each month (or on demand).
"""
import json
import os
from datetime import datetime
from pathlib import Path

import pytz

WIB      = pytz.timezone("Asia/Jakarta")
MODEL    = "claude-opus-4-6"
HIST_DIR = Path(__file__).parent / "history" / "monthly"


# ── Public API ─────────────────────────────────────────────────────────────────

def run_monthly_wrap() -> dict:
    """Fetch sector data, generate wrap, save, return result dict."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from sources.sectors import get_us_sectors, get_idx_sectors, get_crypto_sectors

    now = datetime.now(WIB)
    month_key = now.strftime("%Y-%m")

    print("📊  Fetching sector data in parallel...", end=" ", flush=True)
    with ThreadPoolExecutor(max_workers=3) as ex:
        f_us     = ex.submit(get_us_sectors,     "1mo")
        f_idx    = ex.submit(get_idx_sectors,    "1mo")
        f_crypto = ex.submit(get_crypto_sectors, "1mo")
        us_sectors     = f_us.result()
        idx_sectors    = f_idx.result()
        crypto_sectors = f_crypto.result()
    print("✓")

    data = {
        "month":          month_key,
        "timestamp":      now.isoformat(),
        "us_sectors":     us_sectors,
        "idx_sectors":    idx_sectors,
        "crypto_sectors": crypto_sectors,
    }

    print("🤖  Generating monthly sector wrap...", end=" ", flush=True)
    text = generate_monthly_wrap(data)
    print("✓")

    data["wrap"] = text
    _save(month_key, data)
    return data


def generate_monthly_wrap(data: dict) -> str:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        try:
            return _claude_wrap(data, key)
        except Exception as e:
            print(f"\n⚠️  Claude error ({e.__class__.__name__}), using template.")
    return _template_wrap(data)


# ── Claude ─────────────────────────────────────────────────────────────────────

def _claude_wrap(data: dict, api_key: str) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    with client.messages.stream(
        model=MODEL,
        max_tokens=4096,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": _build_prompt(data)}],
    ) as stream:
        msg = stream.get_final_message()
    return "\n".join(b.text for b in msg.content if b.type == "text")


def _build_prompt(data: dict) -> str:
    month = data.get("month", "")
    lines = [
        f"You are an expert multi-market strategist writing a monthly sector review for {month}.",
        "Your audience: investors tracking US equities, Indonesian stocks, and crypto.",
        "",
        "Guidelines:",
        "- Lead with the 1-2 standout sectors across ALL THREE markets and WHY they moved",
        "- Note rotation signals (what's rotating in/out, cross-market themes)",
        "- For IDX sectors, connect to local macro (BI rate, commodity prices, IDR, capex)",
        "- For Crypto categories, explain what drove rotation (BTC dominance, risk-on/off, narrative shifts)",
        "- End with a 3-bullet forward outlook covering the most important themes across all markets",
        "- Use emojis for scannability. Be specific with numbers.",
        "- Write everything in English",
        "",
        "=== RAW DATA ===",
        "",
        f"Period: {month} (30-day returns)",
        "",
        "US SECTOR ETFs (sorted by return):",
    ]

    for name, d in data.get("us_sectors", {}).items():
        arrow = "▲" if d["return_pct"] >= 0 else "▼"
        lines.append(f"  {arrow} {name} ({d['ticker']}): {d['return_pct']:+.2f}%")

    lines += ["", "IDX SECTORAL INDICES (sorted by return):"]
    for name, d in data.get("idx_sectors", {}).items():
        arrow = "▲" if d["return_pct"] >= 0 else "▼"
        lines.append(f"  {arrow} {name} ({d['ticker']}): {d['return_pct']:+.2f}%")

    lines += ["", "CRYPTO CATEGORIES — avg return of representative tokens (sorted by return):"]
    for name, d in data.get("crypto_sectors", {}).items():
        arrow = "▲" if d["return_pct"] >= 0 else "▼"
        lines.append(f"  {arrow} {name} (rep: {d['ticker']}): {d['return_pct']:+.2f}%")

    lines += [
        "",
        "=== END DATA ===",
        "",
        "Now write the full Monthly Sector Wrap with these sections:",
        f"1. 📅 Monthly Recap — {month} at a glance (2-3 sentences, cross-market theme)",
        "2. 🏆 Top Sectors — US & IDX leaders and why",
        "3. 📉 Laggards — what fell and why",
        "4. 🔄 Rotation Signal — where money is moving (risk-on/off, sector rotation)",
        "5. 🇮🇩 IDX Sector Spotlight — standout local sectors with macro context",
        "6. ₿ Crypto Categories — what led/lagged and the narrative driving it",
        "7. 🔭 Forward Outlook — 3-bullet sector watch for next month (one for each market)",
    ]
    return "\n".join(lines)


# ── Template fallback ──────────────────────────────────────────────────────────

def _template_wrap(data: dict) -> str:
    month = data.get("month", "")
    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━━━",
        f"📅 MONTHLY SECTOR WRAP — {month}",
        "━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]

    us = data.get("us_sectors", {})
    if us:
        items = list(us.items())
        top = [(n, d) for n, d in items if d["return_pct"] > 0]
        bot = [(n, d) for n, d in items if d["return_pct"] <= 0]
        lines += ["🏆 US SECTOR LEADERS:"]
        for name, d in top[:3]:
            lines.append(f"  ▲ {name}: {d['return_pct']:+.2f}%")
        lines += ["", "📉 US SECTOR LAGGARDS:"]
        for name, d in list(reversed(bot))[:3]:
            lines.append(f"  ▼ {name}: {d['return_pct']:+.2f}%")

    idx = data.get("idx_sectors", {})
    if idx:
        items = list(idx.items())
        lines += ["", "🇮🇩 IDX TOP SECTORS:"]
        for name, d in items[:3]:
            lines.append(f"  ▲ {name}: {d['return_pct']:+.2f}%")
        lines += ["", "📉 IDX WEAKEST SECTORS:"]
        for name, d in list(reversed(items))[:3]:
            lines.append(f"  ▼ {name}: {d['return_pct']:+.2f}%")

    crypto = data.get("crypto_sectors", {})
    if crypto:
        items = list(crypto.items())
        lines += ["", "₿ CRYPTO CATEGORY LEADERS:"]
        for name, d in items[:3]:
            lines.append(f"  ▲ {name}: {d['return_pct']:+.2f}%")
        lines += ["", "📉 CRYPTO CATEGORY LAGGARDS:"]
        for name, d in list(reversed(items))[:3]:
            lines.append(f"  ▼ {name}: {d['return_pct']:+.2f}%")

    lines += [
        "",
        "🔭 Forward Outlook:",
        "  • Watch for rotation from defensive to cyclical US sectors if macro data improves.",
        "  • IDX financials may be sensitive to upcoming Bank Indonesia rate decisions.",
        "  • Crypto: monitor BTC dominance — a shift lower typically signals altcoin season.",
    ]
    return "\n".join(lines)


# ── Persistence ────────────────────────────────────────────────────────────────

def _save(month_key: str, data: dict):
    HIST_DIR.mkdir(parents=True, exist_ok=True)
    path = HIST_DIR / f"{month_key}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def list_monthly() -> list:
    if not HIST_DIR.exists():
        return []
    return sorted([p.stem for p in HIST_DIR.glob("*.json")], reverse=True)


def load_monthly(month_key: str) -> dict:
    path = HIST_DIR / f"{month_key}.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}
