"""
Market briefing agent — Claude with web_search + web_fetch tools.
Claude handles all research autonomously; we just collect the output.
"""

import anthropic
from datetime import datetime
import pytz

WIB = pytz.timezone("Asia/Jakarta")

SYSTEM = """\
You are an expert financial market analyst delivering a daily morning briefing
to Indonesian investors. You have access to web search and web fetch tools —
use them to find the most current market data and news available right now.

Guidelines:
- Always search for CURRENT data (today's prices, today's news)
- Include specific numbers: prices, % changes, index levels
- For IDX/IHSG, use Indonesian terminology where natural
- Be concise but complete — investors need facts, not filler
- Flag any data you couldn't verify as "data terbatas"
- Use emojis to make sections easy to scan on mobile
"""

BRIEFING_PROMPT = """\
Today is {date}, {time}. Please research and compile today's morning market briefing.

Search for the latest data on each section below:

━━━━━━━━━━━━━━━━━━━━━━━━
📊 SECTION 1 — US STOCKS
━━━━━━━━━━━━━━━━━━━━━━━━
Search: "S&P 500 today", "NASDAQ today", "Dow Jones today", "US stock market {date}"
- S&P 500, NASDAQ, Dow Jones: current level and % change
- Pre-market movers (if market not open yet) or top movers
- 2–3 key headlines driving US markets

━━━━━━━━━━━━━━━━━━━━━━━━
📊 SECTION 2 — IDX BURSA EFEK INDONESIA
━━━━━━━━━━━━━━━━━━━━━━━━
Search: "IHSG hari ini {date}", "saham IDX hari ini", "bursa efek indonesia today"
Also search: "IHSG today site:investing.com OR site:idx.co.id OR site:cnbcindonesia.com"
- IHSG level dan perubahan % hari ini
- Top 5 saham naik terbesar (gainers)
- Top 5 saham turun terbesar (losers)
- Berita utama pasar saham Indonesia

━━━━━━━━━━━━━━━━━━━━━━━━
📊 SECTION 3 — CRYPTOCURRENCY
━━━━━━━━━━━━━━━━━━━━━━━━
Search: "Bitcoin price today", "crypto market today {date}", "top crypto gainers today"
- BTC and ETH: current price and 24h % change
- Total crypto market cap
- Top 3 gainers and top 3 losers (24h)
- 1–2 key crypto news

━━━━━━━━━━━━━━━━━━━━━━━━
📊 SECTION 4 — NEWS & SOCIAL BUZZ
━━━━━━━━━━━━━━━━━━━━━━━━
Search: "stock market Twitter trending today", "financial news YouTube today",
        "macro economic news {date}", "Fed news today", "economy news Indonesia"
- What's trending on financial Twitter/X right now
- Popular financial YouTube content today
- Key macro events: Fed, inflation, GDP, earnings

━━━━━━━━━━━━━━━━━━━━━━━━
💡 SECTION 5 — OUTLOOK & RINGKASAN
━━━━━━━━━━━━━━━━━━━━━━━━
Based on everything you found:
- Overall market sentiment: 🟢 Bullish / 🔴 Bearish / 🟡 Mixed
- 3 key things to watch today
- One key risk to monitor
- Ringkasan 3 kalimat dalam Bahasa Indonesia untuk investor ritel

Format each section clearly. Use bullet points. Include all specific numbers you found.\
"""


def generate_briefing(client: anthropic.Anthropic) -> str:
    """
    Run Claude with web_search + web_fetch to generate the market briefing.
    Handles pause_turn (server-side tool loop limit) automatically.
    """
    now = datetime.now(WIB)
    date_str = now.strftime("%A, %B %d, %Y")
    time_str = now.strftime("%H:%M WIB")

    prompt = BRIEFING_PROMPT.format(date=date_str, time=time_str)
    messages = [{"role": "user", "content": prompt}]
    full_text = ""

    print(f"🔍 Claude is researching markets for {date_str}...\n")

    for loop in range(8):  # max 8 continuations for pause_turn
        with client.messages.stream(
            model="claude-opus-4-6",
            max_tokens=8192,
            thinking={"type": "adaptive"},
            system=SYSTEM,
            tools=[
                {"type": "web_search_20260209", "name": "web_search"},
                {"type": "web_fetch_20260209", "name": "web_fetch"},
            ],
            messages=messages,
        ) as stream:
            for text in stream.text_stream:
                print(text, end="", flush=True)
                full_text += text

            response = stream.get_final_message()

        if response.stop_reason == "end_turn":
            break

        if response.stop_reason == "pause_turn":
            # Server-side tool loop hit its limit — re-send to continue
            messages = [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": response.content},
            ]
            print(f"\n[continuing search, loop {loop + 1}...]\n")
            continue

        # Any other stop reason — exit
        break

    return full_text
