"""Save and load past briefings as JSON archives."""
import json
from datetime import datetime
from pathlib import Path
import pytz

WIB      = pytz.timezone("Asia/Jakarta")
HIST_DIR = Path(__file__).parent / "history"


def save_briefing(briefing: str, data: dict) -> str:
    """Save a briefing to history/YYYY-MM-DD.json. Returns filename."""
    HIST_DIR.mkdir(exist_ok=True)
    now  = datetime.now(WIB)
    date = now.strftime("%Y-%m-%d")
    path = HIST_DIR / f"{date}.json"

    # If file exists today, keep both (append with timestamp)
    records = []
    if path.exists():
        try:
            records = json.loads(path.read_text())
            if not isinstance(records, list):
                records = [records]
        except Exception:
            records = []

    records.append({
        "timestamp": now.isoformat(),
        "briefing":  briefing,
        "snapshot": {
            "us_indices":    data.get("us_indices", {}),
            "ihsg":          data.get("ihsg", {}),
            "crypto_prices": data.get("crypto_prices", {}),
            "forex":         data.get("forex", {}),
            "commodities":   data.get("commodities", {}),
        },
    })
    path.write_text(json.dumps(records, ensure_ascii=False, indent=2))
    return date


def list_dates() -> list:
    """Return list of available briefing dates (newest first)."""
    if not HIST_DIR.exists():
        return []
    dates = sorted(
        [p.stem for p in HIST_DIR.glob("*.json")],
        reverse=True,
    )
    return dates


def load_briefing(date: str) -> list:
    """Load all briefings for a given date (YYYY-MM-DD)."""
    path = HIST_DIR / f"{date}.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, list) else [data]
    except Exception:
        return []
