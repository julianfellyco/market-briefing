"""Shared utilities: retry-with-backoff, safe fetch, centralised logging."""
import functools
import logging
import time
from pathlib import Path

LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

_fmt = logging.Formatter("%(asctime)s  %(levelname)-8s  %(name)s  %(message)s")
_fh  = logging.FileHandler(LOG_DIR / "app.log")
_fh.setFormatter(_fmt)
_sh  = logging.StreamHandler()
_sh.setFormatter(_fmt)

_root = logging.getLogger()
if not _root.handlers:
    _root.setLevel(logging.INFO)
    _root.addHandler(_sh)
    _root.addHandler(_fh)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def retry(fn=None, *, retries: int = 3, backoff: float = 1.5):
    """Decorator — retries up to `retries` times with exponential backoff."""
    def decorator(f):
        log = get_logger(f.__module__)

        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            delay = 1.0
            for attempt in range(retries):
                try:
                    return f(*args, **kwargs)
                except Exception as e:
                    if attempt < retries - 1:
                        log.warning(f"{f.__name__} attempt {attempt+1} failed ({e}), retry in {delay:.1f}s")
                        time.sleep(delay)
                        delay *= backoff
                    else:
                        log.error(f"{f.__name__} failed after {retries} attempts: {e}")
                        raise
        return wrapper
    return decorator(fn) if fn else decorator


def safe_fetch(fn, *args, default=None, label=""):
    """Call fn(*args); return `default` on any exception and log the failure."""
    log = get_logger("safe_fetch")
    try:
        return fn(*args)
    except Exception as e:
        log.warning(f"{label or fn.__name__} failed: {e}")
        return default
