"""Telegram delivery for the market briefing."""

import httpx

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"
MAX_MSG_LEN = 4096  # Telegram hard limit


def send_telegram(text: str, bot_token: str, chat_id: str) -> bool:
    """
    Send text to a Telegram chat, splitting into chunks if needed.
    Tries Markdown first, falls back to plain text on parse errors.
    """
    chunks = _split(text)
    for chunk in chunks:
        if not _send_chunk(chunk, bot_token, chat_id):
            return False
    return True


def _send_chunk(text: str, token: str, chat_id: str) -> bool:
    url = TELEGRAM_API.format(token=token, method="sendMessage")
    # Try with Markdown
    for parse_mode in ("Markdown", None):
        payload = {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        try:
            r = httpx.post(url, json=payload, timeout=30)
            if r.is_success:
                return True
            if "parse" in r.text.lower() and parse_mode:
                continue  # retry without parse mode
            print(f"  Telegram error: {r.status_code} {r.text[:200]}")
            return False
        except Exception as e:
            print(f"  Telegram request failed: {e}")
            return False
    return False


def _split(text: str) -> list:
    """Split text into Telegram-safe chunks at paragraph boundaries."""
    if len(text) <= MAX_MSG_LEN:
        return [text]
    chunks = []
    while text:
        if len(text) <= MAX_MSG_LEN:
            chunks.append(text)
            break
        pos = text.rfind("\n\n", 0, MAX_MSG_LEN)
        if pos == -1:
            pos = text.rfind("\n", 0, MAX_MSG_LEN)
        if pos == -1:
            pos = MAX_MSG_LEN
        chunks.append(text[:pos])
        text = text[pos:].lstrip()
    return chunks


def send_photo(image_bytes: bytes, caption: str, bot_token: str, chat_id: str) -> bool:
    """Send a PNG image to a Telegram chat."""
    url = TELEGRAM_API.format(token=bot_token, method="sendPhoto")
    try:
        import io
        r = httpx.post(
            url,
            data={"chat_id": chat_id, "caption": caption, "parse_mode": "Markdown"},
            files={"photo": ("chart.png", io.BytesIO(image_bytes), "image/png")},
            timeout=30,
        )
        if r.is_success:
            return True
        # retry without parse mode if parse error
        if "parse" in r.text.lower():
            r2 = httpx.post(
                url,
                data={"chat_id": chat_id, "caption": caption},
                files={"photo": ("chart.png", io.BytesIO(image_bytes), "image/png")},
                timeout=30,
            )
            return r2.is_success
        print(f"  Telegram photo error: {r.status_code} {r.text[:200]}")
        return False
    except Exception as e:
        print(f"  Telegram photo request failed: {e}")
        return False


def get_chat_id(bot_token: str) -> str | None:
    """Auto-detect chat ID from the most recent message sent to the bot."""
    try:
        r = httpx.get(
            TELEGRAM_API.format(token=bot_token, method="getUpdates"),
            timeout=10,
        )
        updates = r.json().get("result", [])
        if updates:
            return str(updates[-1]["message"]["chat"]["id"])
    except Exception as e:
        print(f"  Could not auto-detect chat ID: {e}")
    return None
