"""Output formatting for WebSocket messages."""

from typing import Any


def format_output_message(
    session_id: str,
    line: int,
    content: str,
    stream: str = "stdout",
) -> dict[str, Any]:
    """Format an output line for WebSocket transmission."""
    return {
        "type": "output",
        "session_id": session_id,
        "line": line,
        "content": content,
        "stream": stream,
    }


def format_command_result(
    command_id: int,
    status: str,
    result: str = "",
    session_id: str = "",
) -> dict[str, Any]:
    """Format a command result for WebSocket transmission."""
    msg: dict[str, Any] = {
        "type": "command_result",
        "command_id": command_id,
        "status": status,
        "result": result,
    }
    if session_id:
        msg["session_id"] = session_id
    return msg


def format_process_list(processes: list[dict]) -> dict[str, Any]:
    """Format process list for WebSocket transmission."""
    return {
        "type": "process_list",
        "processes": processes,
    }


def format_identify(machine: str, repos: list[str]) -> dict[str, Any]:
    """Format identify message for WebSocket transmission."""
    return {
        "type": "identify",
        "machine": machine,
        "repos": repos,
    }
