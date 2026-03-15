"""
Market open/closed status for US (NYSE/NASDAQ) and IDX.
Pure datetime logic — no external API needed.
"""
from datetime import datetime, time as dtime
import pytz

ET  = pytz.timezone("America/New_York")
WIB = pytz.timezone("Asia/Jakarta")


def _weekday(dt) -> bool:
    return dt.weekday() < 5  # Mon–Fri


def get_us_status() -> dict:
    now = datetime.now(ET)
    if not _weekday(now):
        return {"status": "closed", "label": "Weekend", "session": None}

    t = now.time()
    if   t < dtime(4,  0):  return {"status": "closed", "label": "Closed",      "session": None}
    elif t < dtime(9, 30):  return {"status": "pre",    "label": "Pre-Market",   "session": "pre"}
    elif t < dtime(16, 0):  return {"status": "open",   "label": "Open",         "session": "regular"}
    elif t < dtime(20, 0):  return {"status": "after",  "label": "After Hours",  "session": "after"}
    else:                   return {"status": "closed", "label": "Closed",       "session": None}


def get_idx_status() -> dict:
    now = datetime.now(WIB)
    if not _weekday(now):
        return {"status": "closed", "label": "Weekend", "session": None}

    t = now.time()
    if   t < dtime(8, 45):  return {"status": "closed", "label": "Closed",       "session": None}
    elif t < dtime(9,  0):  return {"status": "pre",    "label": "Pre-Opening",  "session": "pre"}
    elif t < dtime(11,30):  return {"status": "open",   "label": "Open (S1)",    "session": "regular"}
    elif t < dtime(13,30):  return {"status": "break",  "label": "Lunch Break",  "session": "break"}
    elif t < dtime(15,50):  return {"status": "open",   "label": "Open (S2)",    "session": "regular"}
    else:                   return {"status": "closed", "label": "Closed",       "session": None}


def get_market_status() -> dict:
    return {"us": get_us_status(), "idx": get_idx_status()}
