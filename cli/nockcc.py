"""NockCC CLI — manage sessions and view status from the terminal."""

from __future__ import annotations

import contextlib
import json
from typing import Any

import click
import httpx
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .client import NockCCClient
from .config import (
    clear_active_session,
    get_active_session,
    load_config,
    mask_api_key,
    save_config,
    set_active_session,
)

console = Console()


@click.group()
def cli() -> None:
    """NockCC — Claude Command Center CLI."""


# ---------- config ----------


@cli.group()
def config() -> None:
    """Manage CLI configuration."""


@config.command("init")
def config_init() -> None:
    """Interactive setup — creates ~/.nockcc/config.json."""
    current = load_config()
    api_url = click.prompt("API URL", default=current.get("api_url", "http://localhost:8001"))
    api_key = click.prompt("API Key", default="", hide_input=True)
    save_config({"api_url": api_url, "api_key": api_key})
    console.print("[green]Config saved to ~/.nockcc/config.json[/green]")


@config.command("show")
def config_show() -> None:
    """Display current configuration (API key masked)."""
    cfg = load_config()
    table = Table(title="NockCC Config", show_header=False)
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="white")
    table.add_row("api_url", cfg.get("api_url", ""))
    table.add_row("api_key", mask_api_key(cfg.get("api_key", "")))
    console.print(table)


# ---------- session ----------


@cli.group()
def session() -> None:
    """Session management commands."""


@session.command("start")
@click.option("--agent", required=True, help="Agent name (e.g. claude-code, copilot)")
@click.option("--machine", default="mac", help="Machine identifier")
@click.option("--branch", default="", help="Git branch name")
@click.option("--repo", default="", help="Repository name or owner/name")
@click.option("--task", default="", help="Task description")
def session_start(agent: str, machine: str, branch: str, repo: str, task: str) -> None:
    """Start a new session."""
    # Map CLI-friendly names to model values
    agent_map = {
        "claude-code": "claude_code",
        "claude_code": "claude_code",
        "codex": "codex",
        "copilot": "copilot",
        "gemini": "gemini",
        "kimi": "kimi",
        "chatgpt": "chatgpt",
        "claude-chat": "claude_chat",
        "claude_chat": "claude_chat",
        "other": "other",
    }
    agent_value = agent_map.get(agent, agent)

    client = NockCCClient()
    try:
        result = client.create_session(
            agent=agent_value, machine=machine, branch=branch, repo=repo, task=task
        )
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        console.print(f"[red]Could not reach NockCC API:[/red] {exc}")
        raise SystemExit(1) from None

    if not result.get("success"):
        console.print(f"[red]Error:[/red] {result.get('message', 'Unknown error')}")
        raise SystemExit(1)

    data = result["data"]
    session_id = str(data["id"])
    set_active_session(session_id)

    console.print(
        Panel(
            f"[bold green]Session started[/bold green]\n"
            f"ID: {session_id}\n"
            f"Agent: {data['agent_display']}\n"
            f"Machine: {data['machine_display']}\n"
            f"Branch: {data.get('branch') or '—'}",
            title="NockCC Session",
        )
    )


@session.command("end")
@click.option("--notes", default="", help="Session notes")
@click.option("--status", default="completed", help="End status (completed, failed)")
@click.option("--session-id", default=None, help="Session ID (uses active if omitted)")
def session_end(notes: str, status: str, session_id: str | None) -> None:
    """End the current active session."""
    active_sid = get_active_session()
    sid = session_id or active_sid
    if not sid:
        console.print("[yellow]No active session.[/yellow] Use --session-id to specify one.")
        raise SystemExit(1)

    client = NockCCClient()
    try:
        result = client.end_session(sid, status=status, notes=notes)
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        console.print(f"[red]Could not reach NockCC API:[/red] {exc}")
        raise SystemExit(1) from None

    if not result.get("success"):
        console.print(f"[red]Error:[/red] {result.get('message', 'Unknown error')}")
        raise SystemExit(1)

    # Only clear if we ended the session that was active when command started
    if active_sid and sid == active_sid:
        clear_active_session()
    data = result["data"]
    console.print(
        Panel(
            f"[bold blue]Session ended[/bold blue]\n"
            f"ID: {sid}\n"
            f"Status: {data['status']}\n"
            f"Started: {data['started_at']}\n"
            f"Ended: {data['ended_at']}",
            title="NockCC Session",
        )
    )


@session.command("log")
@click.option("--level", required=True, type=click.Choice(["info", "warning", "error", "success"]))
@click.option("--message", required=True, help="Log message")
@click.option("--session-id", default=None, help="Session ID (uses active if omitted)")
def session_log(level: str, message: str, session_id: str | None) -> None:
    """Add a log entry to the active session."""
    sid = session_id or get_active_session()
    if not sid:
        console.print("[yellow]No active session.[/yellow] Use --session-id to specify one.")
        raise SystemExit(1)

    client = NockCCClient()
    try:
        result = client.add_log(sid, level, message)
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        console.print(f"[red]Could not reach NockCC API:[/red] {exc}")
        raise SystemExit(1) from None

    if not result.get("success"):
        console.print(f"[red]Error:[/red] {result.get('message', 'Unknown error')}")
        raise SystemExit(1)

    console.print(f"[green]Log added[/green] [{level}] {message}")


@session.command("list")
@click.option("--active", is_flag=True, help="Show only active sessions")
@click.option("--agent", default="", help="Filter by agent")
@click.option("--limit", default=20, type=click.IntRange(1), help="Max results")
def session_list(active: bool, agent: str, limit: int) -> None:
    """List sessions."""
    client = NockCCClient()
    try:
        result = client.list_sessions(active=active, agent=agent, limit=limit)
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        console.print(f"[red]Could not reach NockCC API:[/red] {exc}")
        raise SystemExit(1) from None

    if not result.get("success"):
        console.print(f"[red]Error:[/red] {result.get('message', 'Unknown error')}")
        raise SystemExit(1)

    sessions = result["data"]["sessions"]
    if not sessions:
        console.print("[dim]No sessions found.[/dim]")
        return

    table = Table(title="Sessions")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Agent", style="white")
    table.add_column("Machine", style="dim")
    table.add_column("Branch", style="green")
    table.add_column("Status")
    table.add_column("Duration", style="dim")
    table.add_column("Started", style="dim")

    for s in sessions:
        status_style = {
            "active": "green",
            "completed": "blue",
            "failed": "red",
            "paused": "yellow",
            "idle": "dim",
        }.get(s["status"], "white")

        duration = "—"
        if s.get("ended_at") and s.get("started_at"):
            duration = _format_duration(s["started_at"], s["ended_at"])
        elif s["status"] == "active":
            duration = "ongoing"

        started = s.get("started_at", "")[:16].replace("T", " ") if s.get("started_at") else "—"

        table.add_row(
            str(s["id"]),
            s.get("agent_display", s.get("agent", "")),
            s.get("machine_display", s.get("machine", "")),
            s.get("branch") or "—",
            f"[{status_style}]{s['status']}[/{status_style}]",
            duration,
            started,
        )

    console.print(table)


@session.command("status")
def session_status() -> None:
    """Show current active session details."""
    sid = get_active_session()
    if not sid:
        console.print("[dim]No active session.[/dim]")
        return

    client = NockCCClient()
    try:
        result = client.get_session(sid)
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        console.print(f"[red]Could not reach NockCC API:[/red] {exc}")
        raise SystemExit(1) from None

    if not result.get("success"):
        console.print(f"[red]Error:[/red] {result.get('message', 'Unknown error')}")
        raise SystemExit(1)

    data = result["data"]
    lines = [
        f"[bold]Session {sid}[/bold]",
        f"Agent: {data.get('agent_display', data.get('agent', ''))}",
        f"Machine: {data.get('machine_display', data.get('machine', ''))}",
        f"Status: {data['status']}",
        f"Branch: {data.get('branch') or '—'}",
        f"Repo: {data.get('repository') or '—'}",
        f"Started: {data['started_at']}",
    ]
    if data.get("task_description"):
        lines.append(f"Task: {data['task_description']}")

    console.print(Panel("\n".join(lines), title="Active Session"))


# ---------- status (dashboard) ----------


@cli.command("status")
def status() -> None:
    """Show dashboard summary."""
    client = NockCCClient()
    try:
        result = client.dashboard_summary()
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        console.print(f"[red]Could not reach NockCC API:[/red] {exc}")
        raise SystemExit(1) from None

    if not result.get("success"):
        console.print(f"[red]Error:[/red] {result.get('message', 'Unknown error')}")
        raise SystemExit(1)

    data = result["data"]
    lines = [
        f"Active sessions: [green]{data.get('active_sessions', 0)}[/green]",
        f"Open PRs:        [cyan]{data.get('open_prs', 0)}[/cyan]",
        f"Failed CI:       [red]{data.get('failed_ci', 0)}[/red]",
        f"Merged this week: [purple]{data.get('merged_this_week', 0)}[/purple]",
        f"Today's spend:   [dim]{data.get('todays_spend', 'Not available')}[/dim]",
    ]

    console.print(Panel("\n".join(lines), title="NockCC Status"))


# ---------- pipeline ----------


@cli.command("pipeline")
@click.option("--repo", default="", help="Filter by repository name")
@click.option("--limit", default=20, type=click.IntRange(1), help="Max results")
def pipeline(repo: str, limit: int) -> None:
    """Show recent PRs from the pipeline."""
    client = NockCCClient()
    try:
        result = client.pipeline_prs(repo=repo, limit=limit)
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        console.print(f"[red]Could not reach NockCC API:[/red] {exc}")
        raise SystemExit(1) from None

    if not result.get("success"):
        console.print(f"[red]Error:[/red] {result.get('message', 'Unknown error')}")
        raise SystemExit(1)

    prs = result["data"]["prs"]
    if not prs:
        console.print("[dim]No PRs found.[/dim]")
        return

    table = Table(title="Pipeline PRs")
    table.add_column("#", style="cyan", no_wrap=True)
    table.add_column("Title", style="white")
    table.add_column("Repo", style="dim")
    table.add_column("State")
    table.add_column("CI")
    table.add_column("CodeRabbit", style="dim")
    table.add_column("Author", style="dim")

    for pr in prs:
        state_style = {"open": "green", "merged": "purple", "closed": "red"}.get(
            pr["state"], "white"
        )
        ci_style = {"passed": "green", "failed": "red", "running": "yellow"}.get(
            pr["ci_status"], "dim"
        )

        table.add_row(
            str(pr["number"]),
            pr["title"][:60],
            pr.get("repository", ""),
            f"[{state_style}]{pr['state']}[/{state_style}]",
            f"[{ci_style}]{pr['ci_status']}[/{ci_style}]",
            pr.get("coderabbit_status", "—"),
            pr.get("author", ""),
        )

    console.print(table)


# ---------- spend ----------


@cli.group()
def spend() -> None:
    """API spend tracking."""


@spend.command("today")
def spend_today() -> None:
    """Show today's API spend."""
    console.print("[dim]Spend tracking not yet available.[/dim]")


@spend.command("month")
def spend_month() -> None:
    """Show this month's API spend."""
    console.print("[dim]Spend tracking not yet available.[/dim]")


# ---------- wrap ----------


def _detect_agent(cmd: str) -> str:
    """Detect agent type from command name."""
    name = cmd.split("/")[-1].split()[0].lower()
    agent_map = {
        "claude": "claude_code",
        "codex": "codex",
        "copilot": "copilot",
        "gemini": "gemini",
        "kimi": "kimi",
        "chatgpt": "chatgpt",
    }
    return agent_map.get(name, "other")


def _detect_git_info() -> tuple[str, str]:
    """Detect current branch and repo name from git. Returns (branch, repo)."""
    import contextlib
    import subprocess

    branch = ""
    repo = ""
    with contextlib.suppress(subprocess.SubprocessError, FileNotFoundError):
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()

    try:
        remote_url = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        # Extract repo name from URL: git@github.com:owner/repo.git or https://...owner/repo.git
        if remote_url:
            name = remote_url.rstrip("/").rsplit("/", 1)[-1]
            repo = name.removesuffix(".git")
    except (subprocess.SubprocessError, FileNotFoundError):
        pass

    return branch, repo


@cli.command("wrap", context_settings={"ignore_unknown_options": True, "allow_extra_args": True})
@click.argument("command", nargs=-1, type=click.UNPROCESSED)
@click.option("--task", default="", help="Task description")
@click.option("--machine", default="mac", help="Machine identifier")
@click.option("--track", is_flag=True, help="Stream session output to NockCC for phone visibility")
def wrap(command: tuple[str, ...], task: str, machine: str, track: bool) -> None:
    """Wrap a command with automatic session tracking.

    Usage: nockcc wrap -- claude --dangerously-skip-permissions
           nockcc wrap --track -- claude -p "fix the tests"
           cc --track -p "fix the tests"   (via alias)
    """
    import subprocess

    if not command:
        console.print("[red]No command specified.[/red] Usage: nockcc wrap -- <command>")
        raise SystemExit(1)

    # Support --track appearing after -- (e.g. alias cc='nockcc wrap -- claude ...')
    # When the alias already contains --, --track lands in the command tuple.
    if not track and "--track" in command:
        track = True
        command = tuple(arg for arg in command if arg != "--track")

    cmd_str = command[0]
    agent = _detect_agent(cmd_str)
    branch, repo = _detect_git_info()

    if track:
        exit_code = _run_tracked(
            command=command,
            agent=agent,
            machine=machine,
            branch=branch,
            repo=repo,
            task=task,
        )
        raise SystemExit(exit_code)

    # Original non-tracked behavior
    client = NockCCClient()
    try:
        result = client.create_session(
            agent=agent, machine=machine, branch=branch, repo=repo,
            task=task or f"Wrapped: {' '.join(command)}"[:200],
        )
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        console.print(f"[yellow]Could not start session:[/yellow] {exc}")
        console.print("[dim]Running command without session tracking...[/dim]")
        proc = subprocess.run(list(command))
        raise SystemExit(proc.returncode) from None

    if result.get("success"):
        session_id = str(result["data"]["id"])
        set_active_session(session_id)
        console.print(f"[green]Session {session_id} started[/green] ({agent}, {branch or 'no branch'})")
    else:
        console.print(f"[yellow]Session start failed:[/yellow] {result.get('message', '')}")
        console.print("[dim]Running command without session tracking...[/dim]")
        proc = subprocess.run(list(command))
        raise SystemExit(proc.returncode)

    # Run the wrapped command
    try:
        proc = subprocess.run(list(command))
        exit_code = proc.returncode
    except KeyboardInterrupt:
        exit_code = 130
    except FileNotFoundError:
        console.print(f"[red]Command not found:[/red] {cmd_str}")
        exit_code = 127

    # End session — only clear local state if remote end succeeds
    end_status = "completed" if exit_code == 0 else "failed"
    end_ok = False
    try:
        client.end_session(session_id, status=end_status)
        end_ok = True
    except (httpx.HTTPError, json.JSONDecodeError):
        console.print("[yellow]Could not end session remotely — local state preserved[/yellow]")

    if end_ok:
        active_sid = get_active_session()
        if active_sid == session_id:
            clear_active_session()

    console.print(f"[{'green' if exit_code == 0 else 'red'}]Session {session_id} ended ({end_status})[/]")
    raise SystemExit(exit_code)


# ---------- track mode ----------


def _parse_stream_json_line(raw: str) -> dict[str, Any] | None:
    """Parse a single stream-json line from Claude Code output.

    Returns a dict with 'type' and display-relevant fields, or None if unparsable.
    """
    raw = raw.strip()
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def _format_stream_event(event: dict) -> str | None:
    """Convert a stream-json event into a human-readable terminal line."""
    event_type = event.get("type", "")

    if event_type == "assistant":
        # Text response from Claude
        message = event.get("message", {})
        if isinstance(message, dict):
            content = message.get("content", "")
            if isinstance(content, list):
                parts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        parts.append(block.get("text", ""))
                return "\n".join(parts) if parts else None
            return str(content) if content else None
        return str(message) if message else None

    if event_type == "content_block_delta":
        delta = event.get("delta", {})
        if isinstance(delta, dict) and delta.get("type") == "text_delta":
            return delta.get("text", "")
        return None

    if event_type == "result":
        # Final result with cost info
        cost = event.get("cost_usd")
        duration = event.get("duration_ms")
        parts = []
        if cost is not None:
            parts.append(f"Cost: ${cost:.4f}")
        if duration is not None:
            secs = duration / 1000
            parts.append(f"Duration: {secs:.1f}s")
        if parts:
            return f"── {' | '.join(parts)} ──"
        return None

    if event_type == "tool_use":
        tool = event.get("tool", event.get("name", "unknown"))
        return f"── {tool} ──"

    if event_type == "tool_result":
        content = event.get("content", "")
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
            return "\n".join(parts) if parts else None
        return str(content) if content else None

    # For system, error, or other types, return the raw message if present
    if "message" in event and isinstance(event["message"], str):
        return event["message"]
    if "error" in event:
        return f"Error: {event['error']}"

    return None


def _run_tracked(
    command: tuple[str, ...],
    agent: str,
    machine: str,
    branch: str,
    repo: str,
    task: str,
) -> int:
    """Run Claude Code with --track: stream output to both terminal and NockCC."""
    import subprocess
    import sys
    import threading

    client = NockCCClient()

    # Start session with tracking status
    try:
        result = client.create_session(
            agent=agent,
            machine=machine,
            branch=branch,
            repo=repo,
            task=task or f"Tracked: {' '.join(command)}"[:200],
        )
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        console.print(f"[yellow]Could not start session:[/yellow] {exc}")
        console.print("[dim]Running command without tracking...[/dim]")
        proc = subprocess.run(list(command))
        return proc.returncode

    if not result.get("success"):
        console.print(f"[yellow]Session start failed:[/yellow] {result.get('message', '')}")
        proc = subprocess.run(list(command))
        return proc.returncode

    session_id = str(result["data"]["id"])
    set_active_session(session_id)

    # Set status to tracking
    with contextlib.suppress(httpx.HTTPError, json.JSONDecodeError):
        client.post(f"/api/sessions/{session_id}/", {"status": "tracking"})

    console.print(f"[green]Session {session_id} tracking started[/green] ({agent}, {branch or 'no branch'})")
    console.print("[dim]Output streaming to NockCC...[/dim]")

    # Build the claude command with stream-json
    # If the command is claude, inject stream-json flags for structured output
    cmd_list = list(command)
    if cmd_list and cmd_list[0] in ("claude", "claude-code"):
        if "--output-format" not in cmd_list:
            cmd_list.extend(["--output-format", "stream-json"])
        if "--verbose" not in cmd_list:
            cmd_list.append("--verbose")

    # Buffer for batch-pushing output lines to NockCC
    line_counter = 0
    push_buffer: list[dict] = []
    buffer_lock = threading.Lock()

    new_data_event = threading.Event()

    def flush_buffer() -> None:
        nonlocal push_buffer
        with buffer_lock:
            if not push_buffer:
                return
            batch = push_buffer[:]
            push_buffer = []
        try:
            client.push_output(session_id, batch)
        except (httpx.HTTPError, json.JSONDecodeError):
            # Requeue failed batch — SessionOutputBuffer dedupes on (session_id, line_number)
            with buffer_lock:
                push_buffer = batch + push_buffer

    def periodic_flush() -> None:
        """Flush buffer when new data arrives or every 0.3s as a safety net."""
        while not done_event.is_set():
            new_data_event.wait(timeout=0.3)
            new_data_event.clear()
            flush_buffer()

    done_event = threading.Event()

    # Start periodic flush thread
    flush_thread = threading.Thread(target=periodic_flush, daemon=True)
    flush_thread.start()

    proc = None
    stderr_thread = None
    try:
        proc = subprocess.Popen(
            cmd_list,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        def read_stderr() -> None:
            nonlocal line_counter
            assert proc.stderr is not None
            for raw_line in proc.stderr:
                text = raw_line.decode("utf-8", errors="replace").rstrip("\n")
                if text:
                    sys.stderr.write(text + "\n")
                    sys.stderr.flush()
                    with buffer_lock:
                        line_counter += 1
                        push_buffer.append({
                            "line_number": line_counter,
                            "content": text,
                            "stream": "stderr",
                        })
                    new_data_event.set()

        stderr_thread = threading.Thread(target=read_stderr, daemon=True)
        stderr_thread.start()

        assert proc.stdout is not None
        for raw_line in proc.stdout:
            text = raw_line.decode("utf-8", errors="replace").rstrip("\n")
            if not text:
                continue

            # Try to parse as stream-json
            event = _parse_stream_json_line(text)
            if event:
                display = _format_stream_event(event)
                if display:
                    sys.stdout.write(display + "\n")
                    sys.stdout.flush()
                    with buffer_lock:
                        line_counter += 1
                        push_buffer.append({
                            "line_number": line_counter,
                            "content": display,
                            "stream": "stdout",
                        })
                    new_data_event.set()
            else:
                # Not JSON — pass through as raw text
                sys.stdout.write(text + "\n")
                sys.stdout.flush()
                with buffer_lock:
                    line_counter += 1
                    push_buffer.append({
                        "line_number": line_counter,
                        "content": text,
                        "stream": "stdout",
                    })
                new_data_event.set()

        proc.wait()
        exit_code = proc.returncode

    except KeyboardInterrupt:
        if proc:
            proc.terminate()
        exit_code = 130
    except FileNotFoundError:
        console.print(f"[red]Command not found:[/red] {command[0]}")
        exit_code = 127
    finally:
        done_event.set()
        if stderr_thread is not None and stderr_thread.is_alive():
            stderr_thread.join(timeout=5)
        flush_buffer()  # Final flush
        flush_thread.join(timeout=3)

    # Push session exit marker (safe without lock — all threads joined above)
    line_counter += 1
    with contextlib.suppress(httpx.HTTPError, json.JSONDecodeError):
        client.push_output(session_id, [{
            "line_number": line_counter,
            "content": f"── Session exited with code {exit_code} ──",
            "stream": "stdout",
        }])

    # End session
    end_status = "completed" if exit_code == 0 else "failed"
    try:
        client.end_session(session_id, status=end_status)
        active_sid = get_active_session()
        if active_sid == session_id:
            clear_active_session()
    except (httpx.HTTPError, json.JSONDecodeError):
        console.print("[yellow]Could not end session remotely — local state preserved[/yellow]")

    console.print(f"[{'green' if exit_code == 0 else 'red'}]Session {session_id} ended ({end_status})[/]")
    return exit_code


# ---------- helpers ----------


def _format_duration(started: str, ended: str) -> str:
    """Format ISO timestamps into a human duration string."""
    from datetime import datetime

    try:
        start = datetime.fromisoformat(started.replace("Z", "+00:00"))
        end = datetime.fromisoformat(ended.replace("Z", "+00:00"))
        diff = int((end - start).total_seconds())
        if diff < 0:
            return "—"
        hours, remainder = divmod(diff, 3600)
        minutes = remainder // 60
        if hours > 0:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"
    except (ValueError, TypeError):
        return "—"


if __name__ == "__main__":
    cli()
