"""Security checks for incoming commands."""

import hashlib
import hmac
import json
import logging
import os

from .config import AgentConfig

logger = logging.getLogger(__name__)

ALLOWED_COMMAND_TYPES = {
    "start_session",
    "stop_session",
    "send_prompt",
    "list_processes",
    "kill_all",
}


def verify_hmac(payload: dict, signature: str, hmac_key: str) -> bool:
    """Verify HMAC-SHA256 signature of a command payload."""
    if not signature or not hmac_key:
        return False

    payload_bytes = json.dumps(payload, sort_keys=True).encode()
    expected = hmac.new(hmac_key.encode(), payload_bytes, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def validate_command(
    command_type: str,
    payload: dict,
    signature: str,
    config: AgentConfig,
) -> str | None:
    """Validate an incoming command. Returns error message or None if valid."""
    # Check HMAC signature
    if not verify_hmac(payload, signature, config.hmac_key):
        logger.warning("HMAC verification failed for command: %s", command_type)
        return "Invalid HMAC signature"

    # Check command type
    if command_type not in ALLOWED_COMMAND_TYPES:
        logger.warning("Unknown command type: %s", command_type)
        return f"Unknown command type: {command_type}"

    # Check repo allowlist for session commands
    if command_type == "start_session":
        repo = payload.get("repo", "")
        if repo and repo not in config.repos:
            logger.warning("Repo not in allowlist: %s", repo)
            return f"Repo not in allowlist: {repo}"

    # Block raw shell unless explicitly enabled
    if command_type == "run_command" and not config.allow_raw_shell:
        logger.warning("Raw shell commands are disabled")
        return "Raw shell commands are disabled"

    return None


def check_startup_safety() -> list[str]:
    """Check safety conditions at daemon startup. Returns list of errors."""
    errors = []

    if os.getuid() == 0:
        errors.append("Agent must not run as root (UID=0)")

    return errors
