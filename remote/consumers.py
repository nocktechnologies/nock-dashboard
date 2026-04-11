import hashlib
import logging
from urllib.parse import parse_qs

from asgiref.sync import async_to_sync
from channels.generic.websocket import JsonWebsocketConsumer
from django.db import transaction
from django.utils import timezone

from .models import (
    AgentStatus,
    AgentToken,
    CommandAuditLog,
    CommandRequest,
    SessionOutputBuffer,
)

logger = logging.getLogger(__name__)


class AgentConsumer(JsonWebsocketConsumer):
    """WebSocket consumer for the Mac agent daemon.

    Authenticates via token in query string, handles heartbeats,
    output streaming, and command results.
    """

    agent_token = None
    agent_group = None

    def connect(self) -> None:
        token = self._extract_token()
        if not token:
            self._log_auth_failure("No token provided")
            self.close(code=4001)
            return

        token_hash = hashlib.sha256(token.encode()).hexdigest()
        try:
            self.agent_token = AgentToken.objects.get(
                token_hash=token_hash, is_active=True
            )
        except AgentToken.DoesNotExist:
            self._log_auth_failure("Invalid or inactive token")
            self.close(code=4001)
            return

        self.accept()
        self.agent_group = f"agent_{self.agent_token.pk}"
        async_to_sync(self.channel_layer.group_add)(
            self.agent_group, self.channel_name
        )

        AgentStatus.objects.update_or_create(
            agent_token=self.agent_token,
            defaults={
                "is_online": True,
                "connected_at": timezone.now(),
                "last_heartbeat": timezone.now(),
                "channel_name": self.channel_name,
                "ip_address": self._get_client_ip(),
            },
        )
        self.agent_token.last_used_at = timezone.now()
        self.agent_token.save(update_fields=["last_used_at"])

    def disconnect(self, code: int) -> None:
        if self.agent_token:
            AgentStatus.objects.filter(agent_token=self.agent_token).update(
                is_online=False,
                disconnected_at=timezone.now(),
                channel_name="",
            )
        if self.agent_group:
            async_to_sync(self.channel_layer.group_discard)(
                self.agent_group, self.channel_name
            )

    def receive_json(self, content: dict, **kwargs: object) -> None:
        msg_type = content.get("type")
        handlers = {
            "heartbeat": self._handle_heartbeat,
            "identify": self._handle_identify,
            "output": self._handle_output,
            "command_result": self._handle_command_result,
            "process_list": self._handle_process_list,
        }
        handler = handlers.get(msg_type)
        if handler:
            handler(content)
        else:
            self.send_json({
                "type": "error",
                "message": f"Unknown message type: {msg_type}",
            })

    # -- Channel layer handler (called when REST API pushes a command) --

    def agent_command(self, event: dict) -> None:
        """Forward command from channel layer to the WebSocket client."""
        self.send_json(event["data"])

    # -- Message handlers --

    def _handle_heartbeat(self, content: dict) -> None:
        AgentStatus.objects.filter(agent_token=self.agent_token).update(
            last_heartbeat=timezone.now()
        )
        self.send_json({
            "type": "heartbeat_ack",
            "server_time": timezone.now().isoformat(),
        })

    def _handle_identify(self, content: dict) -> None:
        machine = content.get("machine", "")
        AgentStatus.objects.filter(agent_token=self.agent_token).update(
            machine_name=machine
        )

    def _handle_output(self, content: dict) -> None:
        session_id = content.get("session_id", "")
        line_number = content.get("line")
        if not session_id or line_number is None:
            logger.warning(
                "Output message missing session_id or line: %s", content
            )
            self.send_json({
                "type": "error",
                "message": "output requires session_id and line",
            })
            return

        stream = content.get("stream", "stdout")
        text = content.get("content", "")

        logger.info(
            "Output received %s:%d (%s): %.50s",
            session_id, line_number, stream, text,
        )

        SessionOutputBuffer.objects.update_or_create(
            session_id=session_id,
            line_number=line_number,
            defaults={
                "content": text,
                "stream": stream,
            },
        )
        logger.info(
            "Output stored %s:%d in SessionOutputBuffer", session_id, line_number,
        )

    def _handle_command_result(self, content: dict) -> None:
        command_id = content.get("command_id")
        if not command_id:
            return

        valid_statuses = {s.value for s in CommandRequest.Status}
        status = content.get("status", CommandRequest.Status.COMPLETED)
        if status not in valid_statuses:
            logger.warning("Invalid status in command_result: %s", status)
            return

        terminal_statuses = {
            CommandRequest.Status.COMPLETED,
            CommandRequest.Status.FAILED,
            CommandRequest.Status.CANCELLED,
        }

        update_fields: dict[str, object] = {
            "status": status,
            "result": content.get("result", ""),
        }

        # Only set completed_at for terminal statuses
        if status in terminal_statuses:
            update_fields["completed_at"] = timezone.now()

        # Store session_id when the agent reports it (e.g. after start_session)
        session_id = content.get("session_id", "")
        if session_id:
            update_fields["session_id"] = session_id

        with transaction.atomic():
            updated = CommandRequest.objects.filter(pk=command_id).select_for_update()
            updated.update(**update_fields)

            # Propagate session_id to conversation if present
            if session_id:
                cmd = updated.first()
                if cmd and cmd.conversation_id:
                    from .models import ConversationThread

                    ConversationThread.objects.filter(
                        pk=cmd.conversation_id, session_id=""
                    ).update(session_id=session_id)

    def _handle_process_list(self, content: dict) -> None:
        processes = content.get("processes", [])
        AgentStatus.objects.filter(agent_token=self.agent_token).update(
            active_sessions=len(processes)
        )

    # -- Helpers --

    def _extract_token(self) -> str | None:
        query_string = self.scope.get("query_string", b"").decode()
        params = parse_qs(query_string)
        tokens = params.get("token", [])
        return tokens[0] if tokens else None

    def _get_client_ip(self) -> str | None:
        headers = dict(self.scope.get("headers", []))
        forwarded = headers.get(b"x-forwarded-for", b"").decode()
        if forwarded:
            return forwarded.split(",")[0].strip()
        client = self.scope.get("client")
        if client:
            return client[0]
        return None

    def _log_auth_failure(self, reason: str) -> None:
        client_ip = self._get_client_ip()
        logger.warning(
            "WebSocket auth failed from %s: %s", client_ip, reason
        )
        CommandAuditLog.objects.create(
            action="ws_auth_failed",
            source_ip=client_ip,
            details={"reason": reason},
        )
