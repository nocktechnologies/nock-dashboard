"""Subprocess manager for Claude Code sessions."""

import asyncio
import json
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .config import AgentConfig

logger = logging.getLogger(__name__)


@dataclass
class ProcessInfo:
    session_id: str
    repo: str
    pid: int
    process: asyncio.subprocess.Process
    started_at: float = field(default_factory=time.time)


class Executor:
    """Manages Claude Code subprocesses.

    Uses asyncio.create_subprocess_exec (not shell) to prevent command injection.
    All repo paths are validated against the config allowlist before use.

    Claude Code is invoked in non-interactive print mode (-p) with
    stream-json output so each event is flushed immediately, giving
    real-time visibility into tool calls, edits, and responses.
    """

    def __init__(
        self,
        config: AgentConfig,
        output_callback: Callable | None = None,
        completion_callback: Callable | None = None,
    ):
        self.config = config
        self.output_callback = output_callback
        self.completion_callback = completion_callback
        self._processes: dict[str, ProcessInfo] = {}
        self._line_counters: dict[str, int] = {}
        self._output_tasks: dict[str, list[asyncio.Task]] = {}

    @property
    def active_sessions(self) -> list[dict[str, Any]]:
        return [
            {
                "session_id": p.session_id,
                "repo": p.repo,
                "pid": p.pid,
                "uptime": int(time.time() - p.started_at),
            }
            for p in self._processes.values()
            if p.process.returncode is None
        ]

    async def start_session(self, repo: str, prompt: str) -> str:
        """Start a Claude Code session. Returns session_id.

        Uses create_subprocess_exec (no shell) with repo allowlist validation.
        Claude Code runs in print mode (-p) with stream-json output.
        """
        if repo not in self.config.repos:
            raise ValueError(f"Repo not in allowlist: {repo}")

        repo_path = self.config.repos[repo]
        session_id = f"sess-{uuid.uuid4().hex[:12]}"

        # Build command: -p for non-interactive, stream-json for real-time events
        cmd = [
            "claude",
            "-p",
            "--output-format", "stream-json",
            "--verbose",
        ]

        # Add user-configured flags (e.g. --dangerously-skip-permissions)
        if self.config.default_flags:
            for flag in self.config.default_flags.split():
                if flag not in ("-p", "--print", "--output-format", "--verbose"):
                    cmd.append(flag)

        cmd.append(prompt)

        logger.info(
            "Starting session %s in %s: %s",
            session_id,
            repo_path,
            prompt[:80],
        )
        logger.debug("Command: %s", cmd)

        # create_subprocess_exec: safe, no shell, no injection risk
        # No stdin — print mode takes prompt as argument, not interactively
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.DEVNULL,
            cwd=repo_path,
        )

        info = ProcessInfo(
            session_id=session_id,
            repo=repo,
            pid=process.pid,
            process=process,
        )
        self._processes[session_id] = info

        # Start output streaming tasks — tracked so _wait_for_exit can
        # await them and guarantee all output is flushed before signalling
        # session completion.
        stdout_task = asyncio.create_task(
            self._stream_json_output(session_id, process.stdout)
        )
        stderr_task = asyncio.create_task(
            self._stream_output(session_id, process.stderr, "stderr")
        )
        self._output_tasks[session_id] = [stdout_task, stderr_task]
        asyncio.create_task(self._wait_for_exit(session_id))

        return session_id

    async def stop_session(self, session_id: str) -> bool:
        """Stop a session. Returns True if found and stopped."""
        info = self._processes.get(session_id)
        if not info or info.process.returncode is not None:
            return False

        logger.info("Stopping session %s (PID %d)", session_id, info.pid)
        info.process.terminate()

        try:
            await asyncio.wait_for(info.process.wait(), timeout=5.0)
        except TimeoutError:
            logger.warning(
                "Session %s did not terminate, sending SIGKILL", session_id
            )
            info.process.kill()
            await info.process.wait()

        return True

    async def send_prompt(self, session_id: str, prompt: str) -> bool:
        """Send a follow-up prompt to a session.

        In print mode, this starts a NEW Claude Code process that
        resumes the conversation via --continue, since -p processes
        don't accept interactive stdin.
        """
        info = self._processes.get(session_id)
        if not info:
            return False

        repo_path = self.config.repos.get(info.repo, "")
        if not repo_path:
            return False

        cmd = [
            "claude",
            "-p",
            "--output-format", "stream-json",
            "--verbose",
            "--continue",
        ]
        if self.config.default_flags:
            for flag in self.config.default_flags.split():
                if flag not in ("-p", "--print", "--output-format", "--verbose"):
                    cmd.append(flag)
        cmd.append(prompt)

        logger.info("Sending follow-up to session %s: %s", session_id, prompt[:80])

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.DEVNULL,
            cwd=repo_path,
        )

        # Stream output using the same session_id — append to tracked tasks
        stdout_task = asyncio.create_task(
            self._stream_json_output(session_id, process.stdout)
        )
        stderr_task = asyncio.create_task(
            self._stream_output(session_id, process.stderr, "stderr")
        )
        if session_id not in self._output_tasks:
            self._output_tasks[session_id] = []
        self._output_tasks[session_id].extend([stdout_task, stderr_task])

        return True

    def list_processes(self) -> list[dict[str, Any]]:
        """Return info about all tracked processes."""
        return self.active_sessions

    async def kill_all(self) -> int:
        """Kill all tracked subprocesses. Returns count killed."""
        count = 0
        for session_id in list(self._processes.keys()):
            if await self.stop_session(session_id):
                count += 1
        return count

    async def _stream_json_output(
        self,
        session_id: str,
        stream: asyncio.StreamReader | None,
    ) -> None:
        """Read stream-json lines from Claude Code stdout and emit readable content."""
        if stream is None:
            logger.warning("Session %s: stdout stream is None, no output will be captured", session_id)
            return

        raw_line_count = 0
        sent_count = 0
        logger.info("Session %s: starting stdout stream reader", session_id)

        while True:
            try:
                line = await stream.readline()
                if not line:
                    logger.info(
                        "Session %s: stdout EOF after %d raw lines, %d content lines sent",
                        session_id, raw_line_count, sent_count,
                    )
                    break

                raw = line.decode("utf-8", errors="replace").rstrip("\n")
                raw_line_count += 1

                # Log every raw line so we can verify Claude Code is producing output
                logger.info(
                    "Session %s: raw stdout line %d: %.100s",
                    session_id, raw_line_count, raw,
                )

                if not raw:
                    continue

                # Parse stream-json event and extract human-readable content
                content_lines = _extract_content(raw)
                for text in content_lines:
                    self._line_counters[session_id] = (
                        self._line_counters.get(session_id, 0) + 1
                    )
                    line_number = self._line_counters[session_id]
                    if self.output_callback:
                        logger.info(
                            "Session %s: sending line %d: %.50s",
                            session_id, line_number, text,
                        )
                        await self.output_callback(
                            session_id=session_id,
                            line=line_number,
                            content=text,
                            stream="stdout",
                        )
                        sent_count += 1
                    else:
                        logger.warning(
                            "Session %s: no output_callback, dropping line %d",
                            session_id, line_number,
                        )
            except Exception:
                logger.exception(
                    "Error reading stdout for session %s", session_id
                )
                break

    async def _stream_output(
        self,
        session_id: str,
        stream: asyncio.StreamReader | None,
        stream_name: str,
    ) -> None:
        """Read lines from a subprocess stream and forward via callback."""
        if stream is None:
            return

        logger.info("Session %s: starting %s stream reader", session_id, stream_name)

        while True:
            try:
                line = await stream.readline()
                if not line:
                    logger.info("Session %s: %s EOF", session_id, stream_name)
                    break
                # Shared counter per session — prevents stdout/stderr
                # collisions on the (session_id, line_number) unique constraint.
                self._line_counters[session_id] = (
                    self._line_counters.get(session_id, 0) + 1
                )
                line_number = self._line_counters[session_id]
                content = line.decode("utf-8", errors="replace").rstrip("\n")

                if self.output_callback:
                    logger.info(
                        "Session %s: sending %s line %d: %.50s",
                        session_id, stream_name, line_number, content,
                    )
                    await self.output_callback(
                        session_id=session_id,
                        line=line_number,
                        content=content,
                        stream=stream_name,
                    )
            except Exception:
                logger.exception(
                    "Error reading %s for session %s", stream_name, session_id
                )
                break

    async def _wait_for_exit(self, session_id: str) -> None:
        """Wait for process to exit, flush output, and notify completion.

        Critical ordering: we must wait for stdout/stderr tasks to finish
        BEFORE sending session_complete, otherwise the server marks the
        session done before all output lines have been delivered.
        """
        info = self._processes.get(session_id)
        if not info:
            return

        returncode = await info.process.wait()
        logger.info(
            "Session %s process exited with code %d, waiting for output flush...",
            session_id, returncode,
        )

        # Wait for output streaming tasks to finish reading all buffered data
        output_tasks = self._output_tasks.pop(session_id, [])
        if output_tasks:
            await asyncio.gather(*output_tasks, return_exceptions=True)
            logger.info(
                "Session %s: all output streams flushed (%d lines total)",
                session_id, self._line_counters.get(session_id, 0),
            )

        # Now that all output is delivered, send session_complete so the
        # server/UI knows to stop showing "Waiting for output..."
        total_lines = self._line_counters.get(session_id, 0)
        if self.output_callback:
            await self.output_callback(
                session_id=session_id,
                line=total_lines + 1,
                content=f"── Session exited with code {returncode} ──",
                stream="system",
            )
            logger.info(
                "Session %s: session_complete sent (code %d, %d lines)",
                session_id, returncode, total_lines,
            )

        # Notify daemon so it can update the command status to "completed"
        if self.completion_callback:
            await self.completion_callback(
                session_id=session_id,
                return_code=returncode,
            )


def _extract_content(raw: str) -> list[str]:
    """Extract human-readable lines from a stream-json event.

    Returns a list of strings to emit as output lines. Skips noisy
    system/init events and extracts the useful parts of assistant
    messages, tool calls, and results.
    """
    try:
        event = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        # Not JSON — emit as-is (e.g. plain text fallback)
        return [raw] if raw.strip() else []

    event_type = event.get("type", "")

    if event_type == "assistant":
        lines = []
        message = event.get("message", {})
        for block in message.get("content", []):
            if block.get("type") == "text":
                text = block.get("text", "")
                if text.strip():
                    lines.extend(text.splitlines())
            elif block.get("type") == "tool_use":
                name = block.get("name", "unknown")
                tool_input = block.get("input", {})
                summary = _tool_summary(name, tool_input)
                lines.append(f"── {name}: {summary}")
        return lines

    if event_type == "tool_result":
        content = event.get("content", "")
        if isinstance(content, str) and content.strip():
            result_lines = content.splitlines()
            # Limit tool output to first 20 lines to avoid flooding
            if len(result_lines) > 20:
                result_lines = result_lines[:20] + [
                    f"... ({len(result_lines) - 20} more lines)"
                ]
            return result_lines
        return []

    if event_type == "result":
        result_text = event.get("result", "")
        cost = event.get("total_cost_usd")
        lines = []
        if result_text and result_text.strip():
            lines.append("── Result ──")
            lines.extend(result_text.splitlines())
        if cost is not None:
            lines.append(f"── Cost: ${cost:.4f} ──")
        return lines

    # Skip system/init/rate_limit events — too noisy
    return []


def _tool_summary(name: str, tool_input: dict) -> str:
    """One-line summary of a tool call."""
    if name == "Bash":
        cmd = tool_input.get("command", "")
        return cmd[:120] if cmd else "(empty)"
    if name in ("Read", "Glob", "Grep"):
        path = (
            tool_input.get("file_path")
            or tool_input.get("path")
            or tool_input.get("pattern", "")
        )
        return str(path)[:120]
    if name in ("Edit", "Write"):
        path = tool_input.get("file_path", "")
        return str(path)[:120]
    if name == "Agent":
        return tool_input.get("description", "")[:120]
    # Generic fallback
    first_val = next(iter(tool_input.values()), "") if tool_input else ""
    return str(first_val)[:80]
