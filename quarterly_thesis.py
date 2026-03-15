"""
Quarterly big-theme thesis generator.
Runs on the first trading day of each quarter (or on demand).
Produces a forward-looking macro thesis with directional calls.
"""
import json
import os
from datetime import datetime
from pathlib import Path

import pytz

WIB      = pytz.timezone("Asia/Jakarta")
MODEL    = "gemini-2.5-flash"
HIST_DIR = Path(__file__).parent / "history" / "quarterly"


def _quarter_key(dt: datetime) -> str:
    q = (dt.month - 1) // 3 + 1
    return f"{dt.year}-Q{q}"


# ── Public API ─────────────────────────────────────────────────────────────────

def run_quarterly_thesis() -> dict:
    """Fetch macro trend data, generate thesis, save, return result dict."""
    from sources.sectors import get_macro_trends, get_us_sectors, get_idx_sectors

    now = datetime.now(WIB)
    qkey = _quarter_key(now)

    print("📈  Fetching macro trends (90d)...", end=" ", flush=True)
    macro = get_macro_trends("3mo")
    print("✓")

    print("📊  Fetching sector returns (90d)...", end=" ", flush=True)
    us_sectors  = get_us_sectors("3mo")
    idx_sectors = get_idx_sectors("3mo")
    print("✓")

    data = {
        "quarter":     qkey,
        "timestamp":   now.isoformat(),
        "macro":       macro,
        "us_sectors":  us_sectors,
        "idx_sectors": idx_sectors,
    }

    print("🤖  Generating quarterly thesis...", end=" ", flush=True)
    text = generate_quarterly_thesis(data)
    print("✓")

    data["thesis"] = text
    _save(qkey, data)
    return data


def generate_quarterly_thesis(data: dict) -> str:
    key = os.environ.get("GEMINI_API_KEY")
    if key:
        try:
            return _gemini_thesis(data, key)
        except Exception as e:
            print(f"\n⚠️  Gemini error ({e.__class__.__name__}), using template.")
    return _template_thesis(data)


# ── Gemini ─────────────────────────────────────────────────────────────────────

def _gemini_thesis(data: dict, api_key: str) -> str:
    import google.generativeai as genai
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(MODEL)
    response = model.generate_content(_build_prompt(data))
    return response.text


def _build_prompt(data: dict) -> str:
    quarter = data.get("quarter", "")
    lines = [
        f"You are a macro strategist writing the quarterly big-theme thesis for {quarter}.",
        "Your audience: sophisticated Indonesian investors who follow global and local markets.",
        "",
        "Your job: identify the 2-3 dominant macro narratives driving markets this quarter,",
        "assess the risk/reward, and give clear directional calls for the next quarter.",
        "",
        "Guidelines:",
        "- Be opinionated. Name the themes. Don't hedge everything.",
        "- Connect global themes to IDX/IHSG implications explicitly",
        "- Give a Bull case, Bear case, and Base case for the next quarter",
        "- End with a 'Positioning Checklist' — 5 actionable bullet points",
        "- Write everything in English",
        "- Use emojis for section headers. ~600-800 words total.",
        "",
        "=== RAW DATA (90-day returns) ===",
        "",
        "MACRO ASSETS:",
    ]

    for name, d in data.get("macro", {}).items():
        arrow = "▲" if d["return_pct"] >= 0 else "▼"
        lines.append(f"  {arrow} {name}: {d['return_pct']:+.2f}%")

    lines += ["", "US SECTORS (90d, top/bottom 4):"]
    us = list(data.get("us_sectors", {}).items())
    for name, d in us[:4]:
        lines.append(f"  ▲ {name}: {d['return_pct']:+.2f}%")
    for name, d in reversed(us[-4:]):
        lines.append(f"  ▼ {name}: {d['return_pct']:+.2f}%")

    lines += ["", "IDX SECTORS (90d, top/bottom 3):"]
    idx = list(data.get("idx_sectors", {}).items())
    for name, d in idx[:3]:
        lines.append(f"  ▲ {name}: {d['return_pct']:+.2f}%")
    for name, d in reversed(idx[-3:]):
        lines.append(f"  ▼ {name}: {d['return_pct']:+.2f}%")

    lines += [
        "",
        "=== END DATA ===",
        "",
        f"Now write the full Quarterly Big-Theme Thesis for {quarter} with these sections:",
        f"1. 🎯 The Quarter in One Line — a single punchy sentence summarizing {quarter}",
        "2. 📖 Dominant Themes — 2-3 named macro themes with supporting data",
        "3. 🇮🇩 Indonesia Angle — how these themes hit IHSG, IDR, and IDX sectors specifically",
        "4. 🐂 Bull Case / 🐻 Bear Case / 📊 Base Case — for next quarter",
        "5. ✅ Positioning Checklist — 5 actionable bullets for investors",
        "6. 💬 Conclusion — closing paragraph in English with conviction level (High/Medium/Low)",
    ]
    return "\n".join(lines)


# ── Template fallback ──────────────────────────────────────────────────────────

def _template_thesis(data: dict) -> str:
    quarter = data.get("quarter", "")
    macro   = data.get("macro", {})

    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━━━",
        f"🎯 QUARTERLY THESIS — {quarter}",
        "━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "📖 MACRO SNAPSHOT (90d):",
    ]

    for name, d in macro.items():
        arrow = "▲" if d["return_pct"] >= 0 else "▼"
        lines.append(f"  {arrow} {name}: {d['return_pct']:+.2f}%")

    us  = list(data.get("us_sectors", {}).items())
    idx = list(data.get("idx_sectors", {}).items())

    if us:
        best  = us[0]
        worst = us[-1]
        lines += [
            "",
            f"🏆 Best US Sector: {best[0]} ({best[1]['return_pct']:+.2f}%)",
            f"📉 Worst US Sector: {worst[0]} ({worst[1]['return_pct']:+.2f}%)",
        ]

    if idx:
        best  = idx[0]
        worst = idx[-1]
        lines += [
            f"🏆 Best IDX Sector: {best[0]} ({best[1]['return_pct']:+.2f}%)",
            f"📉 Worst IDX Sector: {worst[0]} ({worst[1]['return_pct']:+.2f}%)",
        ]

    sp  = macro.get("S&P 500", {}).get("return_pct", 0)
    btc = macro.get("Bitcoin",  {}).get("return_pct", 0)
    sentiment = "bullish" if (sp + btc) / 2 > 2 else ("bearish" if (sp + btc) / 2 < -2 else "mixed")

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━",
        "✅ POSITIONING CHECKLIST",
        "━━━━━━━━━━━━━━━━━━━━━━━━",
        f"  • Last quarter sentiment: {sentiment}",
        "  • Watch Fed rate direction and its impact on USD/IDR",
        "  • Evaluate commodity stock exposure if oil/gold moves significantly",
        "  • Monitor foreign fund flows (net buy/sell) on IDX",
        "  • Consider rotating into defensive assets if volatility rises",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━",
        "💬 CONCLUSION",
        "━━━━━━━━━━━━━━━━━━━━━━━━",
        f"  Quarter {quarter} showed {sentiment} market dynamics.",
        "  Investors should remain vigilant about shifts in global monetary policy",
        "  and their downstream effects on Indonesian equities.",
        "  Conviction Level: Medium",
    ]
    return "\n".join(lines)


# ── Persistence ────────────────────────────────────────────────────────────────

def _save(qkey: str, data: dict):
    HIST_DIR.mkdir(parents=True, exist_ok=True)
    path = HIST_DIR / f"{qkey}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def list_quarterly() -> list:
    if not HIST_DIR.exists():
        return []
    return sorted([p.stem for p in HIST_DIR.glob("*.json")], reverse=True)


def load_quarterly(qkey: str) -> dict:
    path = HIST_DIR / f"{qkey}.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}
