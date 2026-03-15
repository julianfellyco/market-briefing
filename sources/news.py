"""Fetch financial news via free RSS feeds (feedparser, no API key)."""

import feedparser
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

RSS_FEEDS = {
    "US Markets": [
        "https://feeds.finance.yahoo.com/rss/2.0/headline?s=^GSPC&region=US&lang=en-US",
        "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
        "https://www.cnbc.com/id/20910258/device/rss/rss.html",
    ],
    "Crypto": [
        "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "https://cointelegraph.com/rss",
    ],
    "Indonesia": [
        "https://www.cnbcindonesia.com/RSS",
        "https://ekonomi.bisnis.com/rss",
        "https://market.bisnis.com/rss",
    ],
    "Macro": [
        "https://feeds.reuters.com/reuters/businessNews",
        "https://www.ft.com/?format=rss",
    ],
}

MAX_PER_FEED = 3


def _parse_date(entry) -> datetime:
    for field in ("published", "updated"):
        val = entry.get(field)
        if val:
            try:
                return parsedate_to_datetime(val)
            except Exception:
                pass
    return datetime.now(timezone.utc)


def fetch_news() -> dict:
    """Returns dict of {category: [{"title", "link", "published", "summary"}]}."""
    all_news = {}
    for category, urls in RSS_FEEDS.items():
        items = []
        for url in urls:
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:MAX_PER_FEED]:
                    items.append({
                        "title":     entry.get("title", "").strip(),
                        "link":      entry.get("link", ""),
                        "published": _parse_date(entry).strftime("%Y-%m-%d %H:%M UTC"),
                        "summary":   (entry.get("summary") or entry.get("description") or "")[:300].strip(),
                    })
            except Exception:
                continue
        # deduplicate by title
        seen = set()
        unique = []
        for item in items:
            if item["title"] not in seen:
                seen.add(item["title"])
                unique.append(item)
        all_news[category] = unique[:6]
    return all_news
