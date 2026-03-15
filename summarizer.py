"""
Market briefing formatter.
Uses Claude (claude-opus-4-6) if ANTHROPIC_API_KEY is set,
otherwise falls back to a clean template-based formatter (no API key needed).
"""

import os

MODEL = "claude-opus-4-6"


def generate_briefing(data: dict) -> str:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        try:
            return _claude_briefing(data, key)
        except Exception as e:
            print(f"⚠️  Claude unavailable ({e.__class__.__name__}), using template formatter.")
    return _template_briefing(data)


# ── Claude path ────────────────────────────────────────────────────────────────

def _claude_briefing(data: dict, api_key: str) -> str:
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
    lines = [
        "You are an expert financial market analyst delivering a daily morning briefing.",
        "Below is the raw market data collected right now. Compile it into a clear, well-formatted briefing.",
        "",
        "Guidelines:",
        "- Include specific numbers: prices, % changes, index levels",
        "- Be concise but complete — investors need facts, not filler",
        "- Flag any missing data as 'data unavailable'",
        "- Use emojis to make sections easy to scan on mobile",
        "- Write everything in English",
        "",
        "=== RAW DATA ===",
        "",
    ] + _format_data_lines(data) + [
        "",
        "=== END DATA ===",
        "",
        "Now write the full briefing with these sections:",
        "1. 📊 US Stocks — index levels, key moves, 2-3 headline news",
        "2. 🇮🇩 IDX / IHSG — level, top gainers & losers, key news",
        "3. ₿ Crypto — BTC/ETH prices, market cap, top movers, fear & greed index, key news",
        "4. 💱 Forex — USD/IDR and other major pairs vs IDR",
        "5. 🥇 Commodities — Gold, Oil, key commodity prices",
        "6. 😱 Market Sentiment — Crypto Fear & Greed + Stock/VIX-based Fear & Greed",
        "7. 📰 Macro & Social Buzz — key macro events, trending topics",
        "8. 💡 Outlook & Summary — sentiment (🟢/🔴/🟡), 3 things to watch, key risk, 3-sentence summary",
        "",
        "Format with bullet points. Include all numbers. Be specific.",
    ]
    return "\n".join(lines)


# ── Template path (no API key needed) ─────────────────────────────────────────

def _template_briefing(data: dict) -> str:
    lines = []
    lines += _format_data_lines(data)

    # Sentiment guess
    changes = []
    for d in data.get("us_indices", {}).values():
        if d.get("change_pct") is not None:
            changes.append(d["change_pct"])
    ihsg = data.get("ihsg", {})
    if ihsg.get("change_pct") is not None:
        changes.append(ihsg["change_pct"])
    btc = data.get("crypto_prices", {}).get("bitcoin", {})
    if btc.get("change_24h") is not None:
        changes.append(btc["change_24h"])

    if changes:
        avg = sum(changes) / len(changes)
        if avg > 0.5:
            sentiment = "🟢 Bullish"
        elif avg < -0.5:
            sentiment = "🔴 Bearish"
        else:
            sentiment = "🟡 Mixed"
    else:
        sentiment = "🟡 Mixed"

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━",
        "💡 OUTLOOK & SUMMARY",
        "━━━━━━━━━━━━━━━━━━━━━━━━",
        f"• Market Sentiment: {sentiment}",
        "",
        "📌 3 Things to Watch:",
        "  1. IHSG movement and Asian regional sentiment",
        "  2. US macro data (Fed, inflation, jobs report)",
        "  3. Bitcoin volatility and global crypto markets",
    ]

    ihsg_txt = "unavailable"
    if ihsg.get("price"):
        arrow = "strengthened to" if ihsg["change_pct"] >= 0 else "weakened to"
        ihsg_txt = f"{arrow} {ihsg['price']:,.0f} ({ihsg['change_pct']:+.2f}%)"

    sp_d   = data.get("us_indices", {}).get("S&P 500", {})
    sp_txt = "unavailable"
    if sp_d.get("price"):
        arrow = "rose to" if sp_d["change_pct"] >= 0 else "fell to"
        sp_txt = f"{arrow} {sp_d['price']:,.2f} ({sp_d['change_pct']:+.2f}%)"

    btc_txt = "unavailable"
    if btc.get("price"):
        arrow = "rose to" if btc["change_24h"] >= 0 else "fell to"
        btc_txt = f"{arrow} ${btc['price']:,.0f} ({btc['change_24h']:+.2f}%)"

    lines += [
        "",
        "📋 Summary:",
        f"  US equity markets saw the S&P 500 {sp_txt} in the last session.",
        f"  Domestically, the IHSG {ihsg_txt}, reflecting local investor sentiment.",
        f"  In crypto, Bitcoin {btc_txt} over the past 24 hours.",
    ]

    return "\n".join(lines)


# ── Shared data formatter ──────────────────────────────────────────────────────

def _format_data_lines(data: dict) -> list:
    lines = []

    # US Indices
    lines += ["━━━━━━━━━━━━━━━━━━━━━━━━", "📊 US STOCKS", "━━━━━━━━━━━━━━━━━━━━━━━━"]
    us = data.get("us_indices", {})
    for name, d in us.items():
        if d.get("price"):
            arrow = "📈" if d["change_pct"] >= 0 else "📉"
            lines.append(f"• {arrow} {name}: {d['price']:,.2f} ({d['change_pct']:+.2f}%)")
        else:
            lines.append(f"• ⚠️ {name}: data unavailable")

    # News: US
    news = data.get("news", {})
    us_news = news.get("US Markets", [])
    if us_news:
        lines.append("\n📰 US News:")
        for a in us_news[:3]:
            lines.append(f"  • {a['title']}")

    # IHSG
    lines += ["", "━━━━━━━━━━━━━━━━━━━━━━━━", "🇮🇩 IDX / INDONESIA STOCK EXCHANGE", "━━━━━━━━━━━━━━━━━━━━━━━━"]
    ihsg = data.get("ihsg", {})
    if ihsg.get("price"):
        arrow = "📈" if ihsg["change_pct"] >= 0 else "📉"
        lines.append(f"• {arrow} IHSG: {ihsg['price']:,.2f} ({ihsg['change_pct']:+.2f}%)")
    else:
        lines.append("• ⚠️ IHSG: data unavailable")

    movers = data.get("idx_movers", {})
    if movers.get("gainers"):
        lines.append("\n📈 Top Gainers IDX:")
        for g in movers["gainers"]:
            lines.append(f"  • {g['ticker']}: Rp{g['price']:,} ({g['change_pct']:+.2f}%)")
    if movers.get("losers"):
        lines.append("\n📉 Top Losers IDX:")
        for lo in movers["losers"]:
            lines.append(f"  • {lo['ticker']}: Rp{lo['price']:,} ({lo['change_pct']:+.2f}%)")

    id_news = news.get("Indonesia", [])
    if id_news:
        lines.append("\n📰 Indonesia News:")
        for a in id_news[:3]:
            lines.append(f"  • {a['title']}")

    # Crypto
    lines += ["", "━━━━━━━━━━━━━━━━━━━━━━━━", "₿ CRYPTOCURRENCY", "━━━━━━━━━━━━━━━━━━━━━━━━"]
    cp = data.get("crypto_prices", {})
    btc = cp.get("bitcoin", {})
    eth = cp.get("ethereum", {})
    if btc.get("price"):
        arrow = "📈" if btc["change_24h"] >= 0 else "📉"
        lines.append(f"• {arrow} BTC: ${btc['price']:,.2f} ({btc['change_24h']:+.2f}% 24h)")
    if eth.get("price"):
        arrow = "📈" if eth["change_24h"] >= 0 else "📉"
        lines.append(f"• {arrow} ETH: ${eth['price']:,.2f} ({eth['change_24h']:+.2f}% 24h)")
    gmc = data.get("global_mc", {})
    if gmc.get("total_market_cap_usd"):
        mc_t = gmc["total_market_cap_usd"] / 1e12
        lines.append(f"• Total Market Cap: ${mc_t:.2f}T ({gmc['market_cap_change_24h']:+.2f}% 24h)")

    cm = data.get("top_crypto_movers", {})
    if cm.get("gainers"):
        lines.append("\n🚀 Top Crypto Gainers (24h):")
        for g in cm["gainers"]:
            lines.append(f"  • {g['symbol']}: ${g['price']:,.4g} ({g['change_24h']:+.2f}%)")
    if cm.get("losers"):
        lines.append("\n🔻 Top Crypto Losers (24h):")
        for lo in cm["losers"]:
            lines.append(f"  • {lo['symbol']}: ${lo['price']:,.4g} ({lo['change_24h']:+.2f}%)")

    crypto_news = news.get("Crypto", [])
    if crypto_news:
        lines.append("\n📰 Crypto News:")
        for a in crypto_news[:3]:
            lines.append(f"  • {a['title']}")

    # Forex
    forex = data.get("forex", {})
    if forex:
        lines += ["", "━━━━━━━━━━━━━━━━━━━━━━━━", "💱 FOREX", "━━━━━━━━━━━━━━━━━━━━━━━━"]
        for pair, d in forex.items():
            if d.get("rate"):
                arrow = "📈" if d["change_pct"] >= 0 else "📉"
                lines.append(f"• {arrow} {pair}: Rp{d['rate']:,.2f} ({d['change_pct']:+.2f}%)")

    # Commodities
    commodities = data.get("commodities", {})
    if commodities:
        lines += ["", "━━━━━━━━━━━━━━━━━━━━━━━━", "🥇 COMMODITIES", "━━━━━━━━━━━━━━━━━━━━━━━━"]
        for name, d in commodities.items():
            if d.get("price"):
                arrow = "📈" if d["change_pct"] >= 0 else "📉"
                lines.append(f"• {arrow} {name}: {d['price']:,.2f} {d['unit']} ({d['change_pct']:+.2f}%)")

    # Fear & Greed
    cfg = data.get("crypto_fear_greed", {})
    sfg = data.get("stock_fear_greed", {})
    if cfg.get("value") is not None or sfg.get("score") is not None:
        lines += ["", "━━━━━━━━━━━━━━━━━━━━━━━━", "😱 FEAR & GREED", "━━━━━━━━━━━━━━━━━━━━━━━━"]
        if cfg.get("value") is not None:
            chg = cfg["value"] - cfg.get("prev_value", cfg["value"])
            direction = "▲" if chg > 0 else ("▼" if chg < 0 else "→")
            lines.append(f"• {cfg['emoji']} Crypto F&G: {cfg['value']}/100 — {cfg['classification']} ({direction}{abs(chg)})")
        if sfg.get("score") is not None:
            lines.append(f"• {sfg['emoji']} Stock F&G (VIX {sfg['vix']}): {sfg['score']}/100 — {sfg['classification']}")

    # Macro news
    macro_news = news.get("Macro", [])
    if macro_news:
        lines += ["", "━━━━━━━━━━━━━━━━━━━━━━━━", "🌐 MACRO & GLOBAL NEWS", "━━━━━━━━━━━━━━━━━━━━━━━━"]
        for a in macro_news[:4]:
            lines.append(f"• {a['title']}")

    return lines
