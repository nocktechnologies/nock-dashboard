"""Telegram notification utility for NockCC server-side alerts."""

from __future__ import annotations

import logging

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)


class TelegramNotifier:
    BASE_URL = "https://api.telegram.org/bot{token}/sendMessage"

    @classmethod
    def send(cls, message: str, parse_mode: str = "Markdown") -> dict | None:
        """Send a Telegram message. Returns API response dict or None on failure/disabled."""
        if not getattr(settings, "TELEGRAM_ENABLED", False):
            return None

        token = getattr(settings, "TELEGRAM_BOT_TOKEN", "")
        chat_id = getattr(settings, "TELEGRAM_CHAT_ID", "")
        if not token or not chat_id:
            return None

        url = cls.BASE_URL.format(token=token)
        try:
            response = httpx.post(
                url,
                json={
                    "chat_id": chat_id,
                    "text": message[:4096],
                    "parse_mode": parse_mode,
                },
                timeout=10,
            )
            result = response.json()
            if not result.get("ok"):
                logger.warning("Telegram API error: %s", result.get("description", "unknown"))
            return result
        except (httpx.HTTPError, ValueError, OSError) as exc:
            logger.warning("Telegram send failed: %s", exc)
            return None

