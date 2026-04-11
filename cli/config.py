"""Config loading for NockCC CLI — reads ~/.nockcc/config.json."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

NOCKCC_DIR = Path.home() / ".nockcc"
CONFIG_PATH = NOCKCC_DIR / "config.json"
ACTIVE_SESSION_PATH = NOCKCC_DIR / "active_session"

DEFAULT_CONFIG: dict[str, str] = {
    "api_url": "http://localhost:8001",
    "api_key": "",
}


def ensure_dir() -> None:
    """Create ~/.nockcc/ if it doesn't exist."""
    NOCKCC_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> dict[str, Any]:
    """Load config from disk, returning defaults if missing or malformed."""
    if not CONFIG_PATH.exists():
        return dict(DEFAULT_CONFIG)
    try:
        return json.loads(CONFIG_PATH.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read config file, using defaults: %s", exc)
        return dict(DEFAULT_CONFIG)


def save_config(config: dict[str, Any]) -> None:
    """Write config to disk with owner-only permissions."""
    ensure_dir()
    CONFIG_PATH.write_text(json.dumps(config, indent=2) + "\n")
    os.chmod(CONFIG_PATH, 0o600)


def mask_api_key(key: str) -> str:
    """Mask API key for display — show first 8 and last 4 chars."""
    if len(key) <= 12:
        return "****"
    return key[:8] + "****" + key[-4:]


def get_active_session() -> str | None:
    """Return the active session ID stored on disk, or None."""
    if not ACTIVE_SESSION_PATH.exists():
        return None
    value = ACTIVE_SESSION_PATH.read_text().strip()
    return value if value else None


def set_active_session(session_id: str) -> None:
    """Write the active session ID to disk."""
    ensure_dir()
    ACTIVE_SESSION_PATH.write_text(str(session_id))


def clear_active_session() -> None:
    """Remove the active session file."""
    if ACTIVE_SESSION_PATH.exists():
        ACTIVE_SESSION_PATH.unlink()
