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
MODEL    = "gemini-2.5-flash"
HIST_DIR = Path(__file__).parent / "history" / "monthly"


# ── Public API ─────────────────────────────────────────────────────────────────

def run_monthly_wrap() -> dict:
    """Fetch sector data, generate wrap, save, return result dict."""
    from sources.sectors import get_us_sectors, get_idx_sectors

    now = datetime.now(WIB)
    month_key = now.strftime("%Y-%m")

    print("📊  Fetching US sector ETFs (30d)...", end=" ", flush=True)
    us_sectors = get_us_sectors("1mo")
    print("✓")

    print("🇮🇩  Fetching IDX sectoral indices (30d)...", end=" ", flush=True)
    idx_sectors = get_idx_sectors("1mo")
    print("✓")

    data = {
        "month":       month_key,
        "timestamp":   now.isoformat(),
        "us_sectors":  us_sectors,
        "idx_sectors": idx_sectors,
    }

    print("🤖  Generating monthly sector wrap...", end=" ", flush=True)
    text = generate_monthly_wrap(data)
    print("✓")

    data["wrap"] = text
    _save(month_key, data)
    return data


def generate_monthly_wrap(data: dict) -> str:
    key = os.environ.get("GEMINI_API_KEY")
    if key:
        try:
            return _gemini_wrap(data, key)
        except Exception as e:
            print(f"\n⚠️  Gemini error ({e.__class__.__name__}), using template.")
    return _template_wrap(data)


# ── Gemini ─────────────────────────────────────────────────────────────────────

def _gemini_wrap(data: dict, api_key: str) -> str:
    import requests
    url  = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
    body = {"contents": [{"parts": [{"text": _build_prompt(data)}]}]}
    r    = requests.post(url, json=body, params={"key": api_key}, timeout=60)
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]


def _build_prompt(data: dict) -> str:
    month = data.get("month", "")
    lines = [
        f"You are an expert equity strategist writing a monthly sector review for {month}.",
        "Your audience: investors tracking both global and local markets.",
        "",
        "Guidelines:",
        "- Lead with the 1-2 standout sectors and WHY they moved",
        "- Note rotation signals (what's rotating in/out)",
        "- For IDX sectors, connect to local macro (BI rate, commodity prices, IDR, capex)",
        "- End with a 3-bullet forward outlook: which sectors to watch next month and why",
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

    lines += ["", "IDX SECTORAL (sorted by return):"]
    for name, d in data.get("idx_sectors", {}).items():
        arrow = "▲" if d["return_pct"] >= 0 else "▼"
        lines.append(f"  {arrow} {name} ({d['ticker']}): {d['return_pct']:+.2f}%")

    lines += [
        "",
        "=== END DATA ===",
        "",
        "Now write the full Monthly Sector Wrap with these sections:",
        f"1. 📅 Monthly Recap — {month} at a glance",
        "2. 🏆 Top Sectors — what led and why",
        "3. 📉 Laggards — what fell and why",
        "4. 🔄 Rotation Signal — where money is moving",
        "5. 🇮🇩 IDX Sector Spotlight — standout local sectors with macro context",
        "6. 🔭 Forward Outlook — 3-bullet sector watch for next month",
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
        top   = [(n, d) for n, d in items if d["return_pct"] > 0]
        bot   = [(n, d) for n, d in items if d["return_pct"] <= 0]

        lines += ["🏆 US SECTOR LEADERS:"]
        for name, d in top[:3]:
            lines.append(f"  ▲ {name}: {d['return_pct']:+.2f}%")
        lines += ["", "📉 US SECTOR LAGGARDS:"]
        for name, d in reversed(bot[-3:]):
            lines.append(f"  ▼ {name}: {d['return_pct']:+.2f}%")

    idx = data.get("idx_sectors", {})
    if idx:
        items = list(idx.items())
        lines += ["", "🇮🇩 IDX TOP SECTORS:"]
        for name, d in items[:3]:
            lines.append(f"  ▲ {name}: {d['return_pct']:+.2f}%")
        lines += ["", "📉 IDX WEAKEST SECTORS:"]
        for name, d in reversed(items[-3:]):
            lines.append(f"  ▼ {name}: {d['return_pct']:+.2f}%")

    lines += [
        "",
        "🔭 Forward Outlook:",
        "  • Watch for rotation from defensive to cyclical sectors if macro data improves.",
        "  • IDX financials may be sensitive to upcoming Bank Indonesia rate decisions.",
        "  • Monitor global commodity prices for impact on energy and materials sectors.",
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
