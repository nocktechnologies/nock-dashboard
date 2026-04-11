"""Load and validate agent configuration from ~/.nockcc/agent.json."""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

CONFIG_PATH = Path.home() / ".nockcc" / "agent.json"

REQUIRED_FIELDS = ["server_url", "agent_token", "hmac_key"]


@dataclass
class AgentConfig:
    server_url: str
    agent_token: str
    hmac_key: str
    machine_name: str = "Unknown"
    repos: dict[str, str] = field(default_factory=dict)
    default_flags: str = "--dangerously-skip-permissions"
    allow_raw_shell: bool = False
    kill_on_disconnect: bool = True

    def validate(self) -> list[str]:
        """Return a list of validation errors, empty if valid."""
        errors = []

        if not self.server_url:
            errors.append("server_url is required")
        elif not self.server_url.startswith("wss://"):
            errors.append(
                f"server_url must use wss:// (got: {self.server_url[:20]}...)"
            )

        if not self.agent_token:
            errors.append("agent_token is required")

        if not self.hmac_key:
            errors.append("hmac_key is required")

        for name, path_str in self.repos.items():
            path = Path(path_str)
            if not path.is_absolute():
                errors.append(f"repo '{name}' path must be absolute: {path_str}")

        return errors

    @property
    def repo_names(self) -> list[str]:
        return list(self.repos.keys())


def load_config(path: Path | None = None) -> AgentConfig:
    """Load config from JSON file. Raises FileNotFoundError or ValueError."""
    config_path = path or CONFIG_PATH

    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path) as f:
        data = json.load(f)

    missing = [field for field in REQUIRED_FIELDS if not data.get(field)]
    if missing:
        raise ValueError(f"Missing required config fields: {', '.join(missing)}")

    config = AgentConfig(
        server_url=data["server_url"],
        agent_token=data["agent_token"],
        hmac_key=data["hmac_key"],
        machine_name=data.get("machine_name", "Unknown"),
        repos=data.get("repos", {}),
        default_flags=data.get("default_flags", "--dangerously-skip-permissions"),
        allow_raw_shell=data.get("allow_raw_shell", False),
        kill_on_disconnect=data.get("kill_on_disconnect", True),
    )

    errors = config.validate()
    if errors:
        raise ValueError(f"Config validation failed: {'; '.join(errors)}")

    return config
