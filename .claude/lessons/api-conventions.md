# Lesson: API Response Conventions

## JSON Envelope
All API responses use this envelope:
```json
{"success": bool, "message": str, "data": ...}
```

Never use `{"ok": ...}` or any other shape.

## Error Handling
- Never bare `except:` — always catch specific exception types. Avoid broad `except Exception` unless justified and documented.
- Return appropriate HTTP status codes with the envelope
- Log errors with context before returning response

## Auth
- API endpoints SHOULD require X-API-Key for programmatic access; some views currently allow authenticated session fallback (see `core/auth.py`)
- Views that take slug/id parameters MUST enforce object-level authorization (audit and close existing gaps)
- State-changing views SHOULD enforce CSRF protection; webhook endpoints may be exempt when HMAC verification is implemented
- Current exceptions: many API-key-protected endpoints use `@csrf_exempt` across `intelligence/views.py`, `remote/views.py`, `brain/views.py`, `spend/views.py`, `dashboard/views.py`, and others — these should be audited

## Rate Limiting
- GitHub webhook endpoint: 60 req/min per IP (django-ratelimit)
- Apply rate limiting to any public-facing endpoint
