"""Main agent daemon — WebSocket client with reconnection logic."""

import asyncio
import json
import logging
import signal
import sys

import websockets

from .config import AgentConfig, load_config
from .executor import Executor
from .output import (
    format_command_result,
    format_identify,
    format_output_message,
    format_process_list,
)
from .security import check_startup_safety, validate_command

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 15  # seconds
MAX_RECONNECT_DELAY = 60  # seconds


class AgentDaemon:
    """WebSocket client daemon that connects to NockCC and executes commands."""

    def __init__(self, config: AgentConfig):
        self.config = config
        self.executor = Executor(
            config,
            output_callback=self._send_output,
            completion_callback=self._on_session_complete,
        )
        self._ws = None
        self._running = False
        self._reconnect_delay = 1
        self._session_commands: dict[str, int] = {}  # session_id -> command_id

    async def start(self) -> None:
        """Start the daemon. Runs until stopped."""
        # Safety checks
        errors = check_startup_safety()
        if errors:
            for error in errors:
                logger.error("Startup safety check failed: %s", error)
            sys.exit(1)

        self._running = True

        # Set up signal handlers
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))

        logger.info("Agent daemon starting, connecting to %s", self.config.server_url)

        while self._running:
            try:
                await self._connect_and_run()
            except Exception:
                if not self._running:
                    break
                logger.exception("Connection error")
                logger.info(
                    "Reconnecting in %ds...", self._reconnect_delay
                )
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(
                    self._reconnect_delay * 2, MAX_RECONNECT_DELAY
                )

        logger.info("Agent daemon stopped")

    async def stop(self) -> None:
        """Graceful shutdown: kill all subprocesses and close WebSocket."""
        logger.info("Shutting down...")
        self._running = False

        if self.config.kill_on_disconnect:
            killed = await self.executor.kill_all()
            if killed:
                logger.info("Killed %d session(s)", killed)

        if self._ws:
            await self._ws.close()

    async def _connect_and_run(self) -> None:
        """Connect to server and handle messages until disconnection."""
        url = f"{self.config.server_url}?token={self.config.agent_token}"

        async with websockets.connect(url) as ws:
            self._ws = ws
            self._reconnect_delay = 1  # Reset backoff on successful connection
            logger.info("Connected to NockCC server")

            # Send identify message
            identify_msg = format_identify(
                machine=self.config.machine_name,
                repos=self.config.repo_names,
            )
            await ws.send(json.dumps(identify_msg))

            # Start heartbeat task
            heartbeat_task = asyncio.create_task(self._heartbeat_loop())

            try:
                async for raw_message in ws:
                    try:
                        message = json.loads(raw_message)
                        await self._handle_message(message)
                    except json.JSONDecodeError:
                        logger.warning("Received invalid JSON: %s", raw_message[:100])
            finally:
                heartbeat_task.cancel()
                self._ws = None

                if self.config.kill_on_disconnect and self._running:
                    killed = await self.executor.kill_all()
                    if killed:
                        logger.info(
                            "Killed %d session(s) on disconnect", killed
                        )

    async def _heartbeat_loop(self) -> None:
        """Send heartbeats at regular intervals."""
        while True:
            try:
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                if self._ws:
                    await self._ws.send(json.dumps({"type": "heartbeat"}))
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Heartbeat failed")
                break

    async def _handle_message(self, message: dict) -> None:
        """Route incoming messages to handlers."""
        msg_type = message.get("type")

        if msg_type == "heartbeat_ack":
            return  # Expected, no action needed

        if msg_type == "command":
            await self._handle_command(message)
        elif msg_type == "error":
            logger.warning("Server error: %s", message.get("message", ""))
        else:
            logger.debug("Unhandled message type: %s", msg_type)

    async def _handle_command(self, message: dict) -> None:
        """Validate and execute a command from the server."""
        command_id = message.get("command_id")
        command_type = message.get("command_type", "")
        payload = message.get("payload", {})
        signature = message.get("hmac_signature", "")

        # Validate
        error = validate_command(command_type, payload, signature, self.config)
        if error:
            if command_id:
                await self._send_result(command_id, "failed", error)
            return

        logger.info("Executing command: %s (id=%s)", command_type, command_id)

        try:
            result = await self._execute_command(command_type, payload)
            if command_id:
                if command_type == "start_session" and result.startswith("Session started: "):
                    # Report "running" now; "completed" sent by _on_session_complete
                    session_id = result.split(": ", 1)[1]
                    self._session_commands[session_id] = command_id
                    await self._send_result(
                        command_id, "running", result, session_id=session_id,
                    )
                else:
                    await self._send_result(command_id, "completed", result)
        except Exception as e:
            logger.exception("Command execution failed: %s", command_type)
            if command_id:
                await self._send_result(command_id, "failed", str(e))

    async def _execute_command(self, command_type: str, payload: dict) -> str:
        """Execute a single command and return result string."""
        if command_type == "start_session":
            repo = payload.get("repo", "")
            prompt = payload.get("prompt", "")
            if not repo or not prompt:
                return "Error: repo and prompt are required"
            session_id = await self.executor.start_session(repo, prompt)
            return f"Session started: {session_id}"

        if command_type == "stop_session":
            session_id = payload.get("session_id", "")
            stopped = await self.executor.stop_session(session_id)
            return "Session stopped" if stopped else "Session not found"

        if command_type == "send_prompt":
            session_id = payload.get("session_id", "")
            prompt = payload.get("prompt", "")
            sent = await self.executor.send_prompt(session_id, prompt)
            return "Prompt sent" if sent else "Session not found or not running"

        if command_type == "list_processes":
            processes = self.executor.list_processes()
            # Also send process list update
            if self._ws:
                await self._ws.send(
                    json.dumps(format_process_list(processes))
                )
            return json.dumps(processes)

        if command_type == "kill_all":
            count = await self.executor.kill_all()
            return f"Killed {count} session(s)"

        return f"Unknown command type: {command_type}"

    async def _on_session_complete(
        self, session_id: str, return_code: int,
    ) -> None:
        """Called by executor when a Claude Code process exits."""
        command_id = self._session_commands.pop(session_id, None)
        if command_id:
            await self._send_result(
                command_id,
                "completed",
                f"Session exited (code {return_code})",
                session_id=session_id,
            )

    async def _send_output(self, **kwargs) -> None:
        """Callback for executor to send output lines via WebSocket."""
        if not self._ws:
            logger.warning(
                "Output dropped (no WebSocket): %s line %s",
                kwargs.get("session_id"), kwargs.get("line"),
            )
            return

        msg = format_output_message(**kwargs)
        try:
            await self._ws.send(json.dumps(msg))
            logger.debug(
                "Output sent via WebSocket: %s:%s",
                kwargs.get("session_id"), kwargs.get("line"),
            )
        except Exception:
            logger.exception(
                "Failed to send output %s:%s via WebSocket",
                kwargs.get("session_id"), kwargs.get("line"),
            )

    async def _send_result(
        self,
        command_id: int,
        status: str,
        result: str,
        session_id: str = "",
    ) -> None:
        """Send command result back to server."""
        if self._ws:
            msg = format_command_result(
                command_id, status, result, session_id=session_id,
            )
            await self._ws.send(json.dumps(msg))


def main() -> None:
    """CLI entry point for the agent daemon."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    try:
        config = load_config()
    except FileNotFoundError as e:
        logger.error(str(e))
        logger.error("Run 'python manage.py create_agent_token' on the server first.")
        sys.exit(1)
    except ValueError as e:
        logger.error("Config error: %s", e)
        sys.exit(1)

    daemon = AgentDaemon(config)
    asyncio.run(daemon.start())


if __name__ == "__main__":
    main()
