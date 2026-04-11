# Phase 3 Design Spec — Settings, Models, Telegram & Product Features

**Date:** 2026-04-06
**Branch:** `feature/phase-3-settings-features`
**Codebase:** `terminal-electron/` (React 18 JSX, Vite, Tailwind CSS, Electron 28)
**Approach:** Single branch, atomic commits per feature, parallel agent execution

---

## 1. Model Management (AI Chat Panel)

### Current State
- Hardcoded 5-button model selector (Gemma 3 12B, 27B, Gemma 4, Kit, Mara)
- Ollama status check every 30s via `/api/tags`
- Streaming chat via `ai:ollama:chat` IPC

### Target State
- Dynamic model dropdown populated from Ollama API `GET /api/tags`
- Show model name, size, and context window in dropdown
- "Ollama offline" state with retry button when unreachable
- Remember last-used model in settings (default: `qwen3.5:9b`)
- Kit: detect `claude` / `claude.cmd` in PATH or `%LOCALAPPDATA%\Programs\claude-code\`. Show "Kit (Claude Code)" — clicking opens new terminal tab running `claude` in current project cwd
- Mara: show "Mara (claude.ai)" — clicking opens `https://claude.ai` in default browser via `shell:openExternal`

### Available Models (Alienware RTX 4060 Ti, 8GB VRAM)
- `qwen3.5:9b` — Qwen 3.5 (6.6GB, 256K context, vision + thinking)
- `gemma4:e4b` — Gemma 4 (9.6GB, 256K context, vision + function calling)
- Removed: `gemma3:12b` (old, replaced by Gemma 4)

### Files Modified
- `src/components/AIChatPanel.jsx` — replace button selector with dropdown, dynamic model list
- `electron/ollama-client.js` — add model metadata parsing (size, context window)
- `electron/preload.js` — add `ai:ollama:models` if not already exposed
- `electron/main.js` — wire up model list IPC handler

---

## 2. Settings Expansion

### Current State
9 sections with basic settings: projects, Ollama URL, Claude Code path, terminal/editor fonts, file tree, theme, general, shortcuts (read-only).

### Target State
Full settings page with VS Code-style left sidebar nav. All changes auto-persist (no save button).

#### General
- App theme: Dark (default) / Light / System
- Terminal font family: JetBrains Mono, Fira Code, Cascadia Code, Consolas, monospace
- Terminal font size: slider 10-20px, default 14
- Start minimized to tray: toggle, default off
- Always on top: toggle, default off
- Launch at Windows startup: toggle, default off
- Window opacity: slider 70-100%, default 100

#### AI / Models
- Ollama endpoint URL: text input, default `http://localhost:11434`
- Default model: dropdown populated from Ollama API
- System prompt for AI chat: textarea, default helpful coding assistant
- Temperature: slider 0.0-2.0, default 0.7
- Max tokens: number input, default 4096
- Show thinking/reasoning: toggle (for models that support it like Qwen 3.5)

#### Terminal
- Default shell: dropdown (PowerShell, CMD, Git Bash, WSL — auto-detect available)
- Shell arguments: text input (e.g., `-NoProfile`)
- Scrollback buffer size: number input, default 5000
- Cursor style: dropdown (block, underline, bar)
- Cursor blink: toggle, default on
- Bell sound: toggle, default off
- Copy on select: toggle, default off
- Right-click paste: toggle, default on

#### Notifications
- Enable desktop notifications: toggle, default on
- Notification sound: toggle, default off
- Notify on: PR merged, build complete, session ended, fence event (individual toggles)

#### Telegram
- Enable Telegram notifications: toggle, default off
- Bot token: password input
- Chat ID: text input
- Test notification button
- Quiet hours: start/end time pickers, default 10pm-7am
- What to notify: PR merged, build complete, session ended, fence event (individual toggles)

#### Keyboard Shortcuts
- Customizable keybindings table
- Show current bindings with rebind ability
- Reset to defaults button

#### Data
- Export settings (JSON)
- Import settings (JSON)
- Reset all settings to defaults (confirmation dialog)

#### About
- App version
- Ollama version (from API)
- Models installed (list from API)
- GitHub repo link
- Nock Technologies website link

### Files Modified
- `src/components/Settings.jsx` — major rewrite with section navigation
- `electron/main.js` — new settings defaults, shell detection, window opacity/always-on-top handlers
- `electron/preload.js` — expose new IPC for shell detection, window controls

---

## 3. Telegram Integration

### Architecture
One-way notification forwarding from Terminal to Telegram Bot API. NOT two-way.

### Implementation
- New `electron/telegram-notifier.js` module
- POST `https://api.telegram.org/bot{token}/sendMessage`
- Rate limiting: max 1 message per 5 seconds
- Quiet hours: respect schedule from settings, suppress during quiet hours
- Message format: `Nock Terminal\n{event_type}: {details}\n{timestamp}`
- Events: PR status change, build/test complete, session ended, fence events
- Test button: sends "Nock Terminal — Test notification" to configured chat
- Graceful failure: log errors, don't crash, don't retry endlessly

### Files
- New: `electron/telegram-notifier.js`
- Modified: `src/components/Settings.jsx` (Telegram section)
- Modified: `electron/main.js` (initialize notifier, wire IPC)
- Modified: `electron/preload.js` (expose telegram:test IPC)

---

## 4. Workspace / Project Profiles

### Architecture
Per-project settings stored as JSON files in `%APPDATA%/nock-terminal/projects/{project-hash}.json`.

### Fields
- Preferred AI model for this project
- Custom system prompt for AI chat
- Default terminal shell override
- Environment variables to set when opening terminal
- Preferred Claude Code command (e.g., `claude --dangerously-skip-permissions`)
- Notes field (free text)

### Access
Right-click project card → "Project Settings" to configure.

### Files
- New: `electron/project-profiles.js` (CRUD operations, file-based storage)
- Modified: `src/components/Settings.jsx` or new modal component
- Modified: `src/components/Dashboard.jsx` (context menu on project cards)
- Modified: `electron/main.js` (IPC handlers)
- Modified: `electron/preload.js` (expose project profile IPC)

---

## 5. Session History & Output

### Architecture
Log terminal sessions with metadata. File-based storage in `%APPDATA%/nock-terminal/sessions/`.

### Features
- Log: start time, end time, project, shell, exit code
- Session list panel: browse past sessions with timestamps
- Click past session → view captured output (if capture enabled)
- Export session output as .txt or .md
- Auto-capture: toggle in settings to save session output on close
- Limit: keep last 100 sessions, auto-prune older ones

### Files
- New: `electron/session-history.js` (logging, storage, pruning)
- New: `src/components/SessionHistory.jsx` (list + viewer UI)
- Modified: `electron/terminal-manager.js` (capture output buffer, emit session lifecycle)
- Modified: `electron/main.js` (IPC handlers)
- Modified: `electron/preload.js` (expose session history IPC)
- Modified: `src/components/Sidebar.jsx` (session history panel entry)

---

## 6. Prompt Library

### Architecture
Saved prompt files (.md) stored in `%APPDATA%/nock-terminal/prompts/`.

### Features
- Panel/drawer for browsing saved prompts
- Add prompts: paste text or import from file
- Organize by project tag
- One-click execute: opens new terminal tab, runs `claude` with prompt piped in
- Edit prompts inline with Monaco editor (reuse EditorPane)
- Storage: individual .md files with metadata header

### Files
- New: `electron/prompt-store.js` (CRUD, file-based storage)
- New: `src/components/PromptLibrary.jsx` (browser, editor, execute)
- Modified: `electron/main.js` (IPC handlers)
- Modified: `electron/preload.js` (expose prompt store IPC)
- Modified: `src/components/Sidebar.jsx` (prompt library entry)

---

## 7. Status Bar

### Architecture
Persistent bottom bar across all views. New component rendered at App root level.

### Layout
- Left: current project name + git branch
- Center: active sessions count + Ollama online/offline indicator dot
- Right: context % (if Claude Code session active), session duration timer, clock

### Files
- New: `src/components/StatusBar.jsx`
- Modified: `src/App.jsx` (render StatusBar, pass state props)

---

## 8. UI Polish

### Tab Management
- Drag-and-drop reordering
- Double-click to rename
- Pin tabs (persist across restarts, can't be accidentally closed)

### Context Menus
- Project cards: Open terminal, Open in VS Code, Open in Explorer, Project Settings, Copy path
- Terminal tabs: Rename, Pin/Unpin, Split, Duplicate, Close, Close Others
- File tree items: Open in editor, Open in Explorer, Copy path, Copy content

### Files
- New: `src/components/ContextMenu.jsx` (reusable context menu component)
- Modified: `src/components/TabBar.jsx` (drag-drop, rename, pin, context menu)
- Modified: `src/components/Dashboard.jsx` (project card context menu)
- Modified: `src/components/FileTree.jsx` (file tree context menu)
- Modified: `src/App.jsx` (tab state: pinned flag, order persistence)

---

## Dependency Graph

```
Layer 0 (no deps):       Settings Expansion, Status Bar
Layer 1 (needs settings): Model Management, Telegram, Project Profiles
Layer 2 (needs IPC):      Session History, Prompt Library
Layer 3 (needs all):      UI Polish (context menus, tab management)
```

Layers 0-1 can be built in parallel by agent teams. Layer 2 starts once IPC patterns established. Layer 3 is last.

---

## Design Constraints

- **JSX** — no TypeScript migration this phase
- **Auto-persist** — all settings changes immediate, no save button
- **Error boundaries** — one panel crashing doesn't take down the app
- **Keyboard accessible** — all features reachable via keyboard
- **Nock aesthetic** — pitch black (#0A0A0F), blue-purple gradient (#3B6FD4 → #7C5CFC)
- **Lucide React icons** — consistent icon library
- **DM Sans** for UI text, **JetBrains Mono** for code/terminal

## Commit Plan

```
feat: expand settings page with full sections and auto-persist
feat: add persistent status bar with project, session, and Ollama status
feat: add dynamic model selector with Ollama API and Kit/Mara entries
feat: add Telegram notification integration with quiet hours
feat: add project profiles with per-project settings
feat: add session history and output capture
feat: add prompt library with Monaco editor
feat: add tab management (reorder, rename, pin)
feat: add context menus for cards, tabs, and file tree
```
