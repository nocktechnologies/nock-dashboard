# NockCC CLI

Lightweight Python CLI for the NockCC REST API.

## Install

```bash
cd cli
pip install -e .
```

## Configuration

```bash
nockcc config init      # Interactive setup → ~/.nockcc/config.json
nockcc config show      # Display current config (API key masked)
```

Config file location: `~/.nockcc/config.json`

## Wrap — Auto-Tracked Sessions

The killer feature. Wraps any AI tool command with automatic session tracking:

```bash
nockcc wrap -- claude --dangerously-skip-permissions
nockcc wrap -- codex
nockcc wrap -- copilot
```

What it does:
1. Auto-detects the agent from the command name (`claude` → claude_code, `codex` → codex)
2. Auto-detects branch and repo from the current git directory
3. Starts a session via the NockCC API
4. Runs the wrapped command
5. When the command exits, ends the session (completed if exit 0, failed otherwise)

### Shell Aliases (recommended)

Add to your `~/.zshrc` or `~/.bashrc`:

```bash
alias cc='nockcc wrap -- claude --dangerously-skip-permissions'
alias cx='nockcc wrap -- codex'
```

Now typing `cc` launches Claude Code AND logs the session automatically.

## Session Management

```bash
# Start a session
nockcc session start --agent claude-code --machine mac --branch feature/xyz --repo project-nexus --task "Building dashboard"

# End the active session
nockcc session end --notes "Completed reporting module" --status completed

# Add a log entry
nockcc session log --level info --message "Started PR review"

# List sessions
nockcc session list --active --agent claude-code --limit 10

# Show current active session
nockcc session status
```

## Dashboard & Pipeline

```bash
# Dashboard summary
nockcc status

# Pipeline PRs
nockcc pipeline --repo project-nexus

# Spend (placeholder)
nockcc spend today
nockcc spend month
```
