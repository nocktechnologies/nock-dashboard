# ADR-002: WebSocket for Agent Remote Control

**Status:** Accepted
**Date:** 2026-03-15

## Context
Need to send commands from phone → NockCC → Mac agent and stream output back in real-time.

## Decision
Django Channels WebSocket consumer (`AgentConsumer`) with token-based auth, HMAC-signed commands, and SSE for browser output streaming.

## Rationale
- WebSocket provides persistent bidirectional connection for command dispatch + output streaming
- Token auth (SHA256 hash lookup) avoids session cookie complexity for daemon clients
- HMAC signing ensures command integrity
- SSE to browser is simpler than WebSocket for read-only output streaming
- Channel layer allows REST API to push commands to connected agents

## Consequences
- Requires Daphne (ASGI) in production instead of Gunicorn
- Requires Redis as channel layer backend
- Agent daemon must handle reconnection (auto-reconnect with backoff implemented)
- CommandAuditLog currently logs WebSocket auth failures; full command lifecycle auditing is planned
