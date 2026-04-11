# Lesson: ASGI Deployment Traps on Railway

Tonight's MCP HTTP transport rollout ate 7 commits chasing ghosts before the
real bugs surfaced. Captured here so future me doesn't spend another hour on
any of these.

## Daphne 4.1.2 does NOT implement the ASGI lifespan protocol

- `grep -rln lifespan .venv/.../daphne/` returns **zero matches**. Daphne
  simply doesn't send `lifespan.startup` / `lifespan.shutdown` events.
- If you mount anything that needs lifespan (Starlette, FastAPI, the MCP
  `StreamableHTTPSessionManager`, anyio task groups), it silently never
  starts. Requests then fail with `RuntimeError: Task group is not
  initialized. Make sure to use run().`
- Fix: **use Uvicorn** (`uvicorn config.asgi:application --lifespan on`).
  Channels' websocket consumers still work because `ProtocolTypeRouter`
  dispatches by `scope["type"]` — the ASGI server underneath is irrelevant.
- Do NOT try to route `"lifespan": http_router` through
  `ProtocolTypeRouter` and call it fixed. That just routes an event Daphne
  never emits.

## Railway's Railpack 0.23 cached build layer survived 3 commits in a row

- I added `mcp>=1.23.0,<2.0.0` to `requirements.txt`. Railpack kept
  building from a 33-line snapshot that didn't include it. Pip's
  `Collecting` output stopped at `pytest-django==4.8.0 (from line 33)`
  with zero `mcp` / `starlette` / `pytest-asyncio`. Daphne then crashed
  at import with `ModuleNotFoundError: No module named 'mcp'` and
  Railway rolled back to the previous deploy — leaving 404s on `/mcp/*`
  while the health checks on other endpoints kept passing.
- Reordering `requirements.txt` (putting `mcp` at line 4 instead of 38)
  did not bust the cache.
- Setting `[build].buildCommand = "pip install --no-cache-dir -r
  requirements.txt"` in `railway.toml` did not take effect — Railpack
  ignores that field. That knob is for Nixpacks.
- **Fix**: force builder via `[build].builder = "NIXPACKS"` in
  `railway.toml`. Nixpacks has an independent build graph and honors
  `buildCommand`, so the cached Railpack layer is untouchable from it.
- Follow-up: purge the Railpack build cache via the Railway web UI (not
  CLI) once the underlying bug is understood so we can reconsider
  Railpack later.

## Don't read `railway logs -s web -b` without `--latest` when debugging a failed deploy

- Railway's default `railway logs -s <service> -b` shows the most recent
  **successful** build. When your deploy is failing and rolled back,
  that's the PREVIOUS build — so you read stale output and chase the
  wrong theory.
- `--latest` gets the failing one: `railway logs -s web -b --latest`.
  This is how I finally saw the real `ERROR: Cannot install ... pytest
  conflicts with pytest-asyncio` — three commits after I should have.
- Same applies to deployment logs: `railway logs -s worker --latest` to
  see the failing deploy's tracebacks, not the rolled-back working one.

## Starlette's `Mount` does NOT rewrite `scope["path"]`

- `Mount("/mcp", app=sub_app)` compiles its path regex as
  `/mcp/{path:path}`. Requests to `/mcp/foo` reach `sub_app` with
  **`scope["path"] == "/mcp/foo"` unchanged** and
  `scope["root_path"] == "/mcp"`.
- If your sub-app's middleware checks `scope["path"]` directly (e.g.
  for a `/health` exemption), it'll see `/mcp/health` and fail the
  comparison. Compute the relative path as
  `scope["path"][len(scope["root_path"]):]`, don't trust bare `path`.
- Separately, `Mount("/mcp", ...)` compiles a regex that matches
  `/mcp/...` but **NOT the bare `/mcp`** — the latter 404s. claude.ai
  custom connectors probe the bare path, so you need an explicit
  `Route("/mcp")` that 308s to `/mcp/` before the mount.

## pytest version pins bite when adding pytest-asyncio

- `pytest==8.1.1` in `requirements.txt` (pre-existing) + adding
  `pytest-asyncio==1.3.0` = `ResolutionImpossible`. `pytest-asyncio
  1.3.0` requires `pytest>=8.2`.
- Check dep compatibility locally with
  `.venv/bin/pip install --dry-run -r requirements.txt` BEFORE pushing.
  Local `.venv` may already have a newer pytest that masks this.

## claude.ai custom connectors are OAuth-only

- A plain bearer-token MCP server that works with `curl` + Claude Code
  stdio will **silently fail** when added to claude.ai as a custom
  connector. The connector UI runs a full OAuth 2.1 discovery dance
  (RFC 9728 + 8414 + 7591 + 7636) and bails before sending any
  initialize request if discovery returns 404.
- Required endpoints: `/.well-known/oauth-protected-resource/<resource>`,
  `/.well-known/oauth-authorization-server`, `/oauth/register`,
  `/oauth/authorize`, `/oauth/token`. Plus a `resource_metadata=` attr
  on the 401 `WWW-Authenticate` header.
- For a single-user instance you can cheat: auto-approve authorize
  with no consent screen, issue the existing API key AS the access
  token. See `core/oauth/` for the pattern — do NOT copy it into a
  multi-tenant service.
