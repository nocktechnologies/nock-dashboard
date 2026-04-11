# Phase 3 — Settings, Models, Telegram & Product Features

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add full settings page, dynamic Ollama model selector, Telegram notifications, project profiles, session history, prompt library, status bar, and UI polish to the Nock Terminal Electron app.

**Architecture:** Single-branch (`feature/phase-3-settings-features`), atomic commits per feature. React 18 JSX + Tailwind CSS in `terminal-electron/`. Electron main process services in `terminal-electron/electron/`. Settings via `electron-store`. New file-based storage in `%APPDATA%/nock-terminal/` for sessions, prompts, project profiles. `lucide-react` for all new icons.

**Tech Stack:** Electron 28, React 18, Vite 5, Tailwind CSS 3.4, xterm.js, Monaco editor, node-pty, electron-store, lucide-react (new dep)

---

## File Structure

### New Files
| File | Responsibility |
|------|---------------|
| `electron/telegram-notifier.js` | Telegram Bot API client — rate-limited, quiet hours, message formatting |
| `electron/project-profiles.js` | Per-project settings CRUD — file-based JSON in `%APPDATA%/nock-terminal/projects/` |
| `electron/session-history.js` | Terminal session logging — metadata + optional output capture, auto-prune |
| `electron/prompt-store.js` | Prompt library CRUD — .md files with YAML frontmatter in `%APPDATA%/nock-terminal/prompts/` |
| `src/components/StatusBar.jsx` | Persistent bottom bar — project, branch, sessions, Ollama status, clock |
| `src/components/SessionHistory.jsx` | Session history list + output viewer panel |
| `src/components/PromptLibrary.jsx` | Prompt browser, editor, tag filter, one-click execute |
| `src/components/ContextMenu.jsx` | Reusable positioned context menu component |
| `src/components/ProjectSettingsModal.jsx` | Modal dialog for per-project settings |

### Modified Files
| File | Changes |
|------|---------|
| `package.json` | Add `lucide-react` dependency |
| `electron/main.js` | New store defaults, new service initialization, new IPC handlers for telegram/profiles/sessions/prompts/shell-detect/window-controls |
| `electron/preload.js` | Expose new IPC namespaces: telegram, profiles, sessionHistory, prompts, system |
| `electron/ollama-client.js` | Enhance `listModels()` to return full metadata (size, parameter count, context window) |
| `electron/terminal-manager.js` | Add output capture buffer, emit session lifecycle events (start/end with metadata) |
| `src/components/Settings.jsx` | Complete rewrite: VS Code-style sidebar nav, all new sections (General, AI/Models, Terminal, Notifications, Telegram, Shortcuts, Data, About) |
| `src/components/AIChatPanel.jsx` | Replace hardcoded model buttons with dynamic dropdown, Kit/Mara special entries |
| `src/App.jsx` | Add StatusBar, pass state, tab pinning/renaming/reordering state, sidebar panels for session history + prompt library |
| `src/components/TabBar.jsx` | Add drag-drop reorder, double-click rename, pin indicator, expanded context menu |
| `src/components/Sidebar.jsx` | Add Session History and Prompt Library nav entries + panels |
| `src/components/Dashboard.jsx` | Add right-click context menu on project cards |
| `src/components/FileTree.jsx` | Add right-click context menu on file/folder items |

---

## Task 1: Install lucide-react and create feature branch

**Files:**
- Modify: `terminal-electron/package.json`

- [ ] **Step 1: Create feature branch**

```bash
cd terminal-electron
git checkout -b feature/phase-3-settings-features
```

- [ ] **Step 2: Install lucide-react**

```bash
cd terminal-electron
npm install lucide-react
```

- [ ] **Step 3: Verify installation**

```bash
cd terminal-electron
node -e "require('lucide-react')" 2>&1 || echo "OK - ESM module, verified in package.json"
grep lucide-react package.json
```

Expected: `lucide-react` appears in dependencies.

- [ ] **Step 4: Commit**

```bash
git add package.json package-lock.json
git commit -m "chore: add lucide-react icon library for Phase 3 UI"
```

---

## Task 2: Settings Expansion — Full Rewrite

**Files:**
- Modify: `terminal-electron/src/components/Settings.jsx` (complete rewrite)
- Modify: `terminal-electron/electron/main.js` (new store defaults, new IPC handlers)
- Modify: `terminal-electron/electron/preload.js` (expose new IPC)

- [ ] **Step 1: Add new store defaults in main.js**

In `terminal-electron/electron/main.js`, replace the `store` defaults object (lines 13-33) with expanded defaults:

```javascript
const store = new Store({
  defaults: {
    windowBounds: { width: 1400, height: 900 },
    // General
    theme: 'dark',
    startMinimized: false,
    alwaysOnTop: false,
    launchAtStartup: false,
    windowOpacity: 100,
    // AI / Models
    ollamaUrl: 'http://localhost:11434',
    defaultModel: 'qwen3.5:9b',
    systemPrompt: 'You are a helpful coding assistant. Be concise and precise.',
    temperature: 0.7,
    maxTokens: 4096,
    showThinking: false,
    // Claude Code
    claudeCodePath: '',
    maraBriefPath: '',
    // Terminal
    terminalFontSize: 16,
    terminalFontFamily: "'JetBrains Mono', 'Consolas', monospace",
    defaultShell: '',
    shellArgs: '',
    scrollbackSize: 5000,
    cursorStyle: 'block',
    cursorBlink: true,
    bellSound: false,
    copyOnSelect: false,
    rightClickPaste: true,
    // Editor
    editorFontFamily: "'JetBrains Mono', 'Consolas', monospace",
    editorFontSize: 15,
    editorMinimap: false,
    editorWordWrap: false,
    // File Tree
    fileTreeOpen: true,
    showDotfiles: false,
    // Notifications
    desktopNotifications: true,
    notificationSound: false,
    notifyPrMerged: true,
    notifyBuildComplete: true,
    notifySessionEnded: true,
    notifyFenceEvent: false,
    // Telegram
    telegramEnabled: false,
    telegramBotToken: '',
    telegramChatId: '',
    telegramQuietStart: '22:00',
    telegramQuietEnd: '07:00',
    telegramNotifyPrMerged: true,
    telegramNotifyBuildComplete: true,
    telegramNotifySessionEnded: true,
    telegramNotifyFenceEvent: false,
    // Session capture
    autoCaptureSessions: false,
    // Layout
    sidebarCollapsed: false,
    // Projects
    devRoots: process.platform === 'win32' ? ['C:\\Dev'] : [],
    projectSkipList: ['Gym-App', 'github.com-kkwills13-nock-technologies-site'],
  },
});
```

- [ ] **Step 2: Add shell detection and window control IPC handlers in main.js**

Add these IPC handlers inside the `registerIPC()` function in `terminal-electron/electron/main.js`, after the existing settings handlers (after line 244):

```javascript
  // System info
  ipcMain.handle('system:detectShells', async () => {
    const fs = require('fs');
    const { spawnSync } = require('child_process');
    const shells = [];

    if (process.platform === 'win32') {
      // PowerShell 7
      const pwshPaths = [
        path.join(process.env.ProgramFiles || '', 'PowerShell', '7', 'pwsh.exe'),
        path.join(process.env['ProgramFiles(x86)'] || '', 'PowerShell', '7', 'pwsh.exe'),
      ];
      for (const p of pwshPaths) {
        try { if (fs.existsSync(p)) { shells.push({ name: 'PowerShell 7', path: p }); break; } } catch {}
      }
      if (!shells.find(s => s.name === 'PowerShell 7')) {
        try {
          const res = spawnSync('where', ['pwsh.exe'], { encoding: 'utf-8', windowsHide: true, timeout: 3000 });
          if (res.status === 0 && res.stdout) {
            const match = res.stdout.split(/\r?\n/).find(l => l.trim());
            if (match) shells.push({ name: 'PowerShell 7', path: match.trim() });
          }
        } catch {}
      }

      // Windows PowerShell 5.1
      const ps51 = path.join(process.env.SystemRoot || 'C:\\Windows', 'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe');
      try { if (fs.existsSync(ps51)) shells.push({ name: 'Windows PowerShell', path: ps51 }); } catch {}

      // CMD
      if (process.env.COMSPEC) shells.push({ name: 'Command Prompt', path: process.env.COMSPEC });

      // Git Bash
      const gitBashPaths = [
        path.join(process.env.ProgramFiles || '', 'Git', 'bin', 'bash.exe'),
        path.join(process.env['ProgramFiles(x86)'] || '', 'Git', 'bin', 'bash.exe'),
        'C:\\Program Files\\Git\\bin\\bash.exe',
      ];
      for (const p of gitBashPaths) {
        try { if (fs.existsSync(p)) { shells.push({ name: 'Git Bash', path: p }); break; } } catch {}
      }

      // WSL
      try {
        const res = spawnSync('where', ['wsl.exe'], { encoding: 'utf-8', windowsHide: true, timeout: 3000 });
        if (res.status === 0) shells.push({ name: 'WSL', path: 'wsl.exe' });
      } catch {}
    } else {
      shells.push({ name: 'Bash', path: '/bin/bash' });
      try { if (fs.existsSync('/bin/zsh')) shells.push({ name: 'Zsh', path: '/bin/zsh' }); } catch {}
    }
    return shells;
  });

  ipcMain.handle('system:ollamaVersion', async () => {
    try {
      const response = await ollamaClient._fetch('/api/version', 'GET');
      return response.version || 'unknown';
    } catch {
      return 'unreachable';
    }
  });

  ipcMain.handle('system:appVersion', () => {
    return app.getVersion();
  });

  // Window controls for settings
  ipcMain.on('window:setAlwaysOnTop', (_, value) => {
    mainWindow?.setAlwaysOnTop(!!value);
  });

  ipcMain.on('window:setOpacity', (_, value) => {
    const opacity = Math.max(0.7, Math.min(1.0, value / 100));
    mainWindow?.setOpacity(opacity);
  });
```

Also update the existing `settings:set` handler to react to new settings (replace the handler at lines 229-244):

```javascript
  ipcMain.on('settings:set', (_, { key, value }) => {
    store.set(key, value);
    if (key === 'ollamaUrl') ollamaClient.setUrl(value);
    if (key === 'claudeCodePath') claudeCodeClient.setBinaryPath(value);
    if (key === 'devRoots' || key === 'projectSkipList') {
      sessionDiscovery.setConfig({ devRoots: store.get('devRoots'), skipList: store.get('projectSkipList') });
    }
    if (key === 'alwaysOnTop') mainWindow?.setAlwaysOnTop(!!value);
    if (key === 'windowOpacity') {
      const opacity = Math.max(0.7, Math.min(1.0, value / 100));
      mainWindow?.setOpacity(opacity);
    }
    if (key === 'launchAtStartup') {
      app.setLoginItemSettings({ openAtLogin: !!value });
    }
  });
```

- [ ] **Step 3: Expose new IPC in preload.js**

Add to the `window.nockTerminal` object in `terminal-electron/electron/preload.js`, after the `process` section (after line 103):

```javascript
  // System
  system: {
    detectShells: () => ipcRenderer.invoke('system:detectShells'),
    ollamaVersion: () => ipcRenderer.invoke('system:ollamaVersion'),
    appVersion: () => ipcRenderer.invoke('system:appVersion'),
    setAlwaysOnTop: (value) => ipcRenderer.send('window:setAlwaysOnTop', value),
    setOpacity: (value) => ipcRenderer.send('window:setOpacity', value),
  },
```

- [ ] **Step 4: Rewrite Settings.jsx**

Replace the entire content of `terminal-electron/src/components/Settings.jsx` with the new VS Code-style settings page. The component has:
- Left sidebar with section navigation (General, AI/Models, Terminal, Editor, File Tree, Notifications, Telegram, Shortcuts, Data, About)
- Right content panel showing active section
- All settings auto-persist via `updateSetting()`
- Uses lucide-react icons for section nav

```jsx
import React, { useState, useEffect, useCallback } from 'react';
import {
  Settings2, Cpu, TerminalSquare, Code2, FolderTree,
  Bell, Send, Keyboard, Database, Info,
  ChevronDown, RotateCcw, Download, Upload, ExternalLink,
} from 'lucide-react';

const SECTIONS = [
  { id: 'general', label: 'General', icon: Settings2 },
  { id: 'ai', label: 'AI / Models', icon: Cpu },
  { id: 'terminal', label: 'Terminal', icon: TerminalSquare },
  { id: 'editor', label: 'Editor', icon: Code2 },
  { id: 'filetree', label: 'File Tree', icon: FolderTree },
  { id: 'notifications', label: 'Notifications', icon: Bell },
  { id: 'telegram', label: 'Telegram', icon: Send },
  { id: 'shortcuts', label: 'Shortcuts', icon: Keyboard },
  { id: 'data', label: 'Data', icon: Database },
  { id: 'about', label: 'About', icon: Info },
];

const FONT_OPTIONS = [
  { value: "'JetBrains Mono', 'Consolas', monospace", label: 'JetBrains Mono' },
  { value: "'Fira Code', 'Consolas', monospace", label: 'Fira Code' },
  { value: "'Cascadia Code', monospace", label: 'Cascadia Code' },
  { value: "'Consolas', monospace", label: 'Consolas' },
  { value: "monospace", label: 'System Monospace' },
];

const CURSOR_OPTIONS = [
  { value: 'block', label: 'Block' },
  { value: 'underline', label: 'Underline' },
  { value: 'bar', label: 'Bar' },
];

export default function Settings() {
  const [activeSection, setActiveSection] = useState('general');
  const [settings, setSettings] = useState({});
  const [saved, setSaved] = useState(false);
  const [shells, setShells] = useState([]);
  const [ollamaModels, setOllamaModels] = useState([]);
  const [ollamaVersion, setOllamaVersion] = useState('—');
  const [appVersion, setAppVersion] = useState('—');
  // Drafts for multi-line textareas
  const [devRootsDraft, setDevRootsDraft] = useState('');
  const [skipListDraft, setSkipListDraft] = useState('');
  const [systemPromptDraft, setSystemPromptDraft] = useState('');

  useEffect(() => {
    window.nockTerminal.settings.getAll().then(all => {
      setSettings(all);
      setDevRootsDraft((all.devRoots || []).join('\n'));
      setSkipListDraft((all.projectSkipList || []).join('\n'));
      setSystemPromptDraft(all.systemPrompt || '');
    });
    window.nockTerminal.system.detectShells().then(setShells);
    window.nockTerminal.system.appVersion().then(setAppVersion);
    window.nockTerminal.system.ollamaVersion().then(setOllamaVersion);
    window.nockTerminal.ai.ollama.models().then(setOllamaModels);
  }, []);

  const updateSetting = useCallback((key, value) => {
    setSettings(prev => ({ ...prev, [key]: value }));
    window.nockTerminal.settings.set(key, value);
    setSaved(true);
    setTimeout(() => setSaved(false), 1500);
  }, []);

  const commitListSetting = useCallback((key, draft) => {
    const parsed = draft.split('\n').map(s => s.trim()).filter(Boolean);
    updateSetting(key, parsed);
  }, [updateSetting]);

  const exportSettings = useCallback(async () => {
    const all = await window.nockTerminal.settings.getAll();
    const blob = new Blob([JSON.stringify(all, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'nock-terminal-settings.json';
    a.click();
    URL.revokeObjectURL(url);
  }, []);

  const importSettings = useCallback(() => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';
    input.onchange = async (e) => {
      const file = e.target.files[0];
      if (!file) return;
      const text = await file.text();
      try {
        const imported = JSON.parse(text);
        for (const [key, value] of Object.entries(imported)) {
          if (key === 'windowBounds') continue; // Don't overwrite window position
          updateSetting(key, value);
        }
        setSettings(prev => ({ ...prev, ...imported }));
      } catch {
        alert('Invalid settings file');
      }
    };
    input.click();
  }, [updateSetting]);

  const resetSettings = useCallback(() => {
    if (!confirm('Reset all settings to defaults? This cannot be undone.')) return;
    window.nockTerminal.settings.getAll().then(all => {
      // We can't easily get defaults from electron-store via IPC, so reload the page
      // The store constructor defaults will apply on next launch
      for (const key of Object.keys(all)) {
        if (key === 'windowBounds') continue;
        window.nockTerminal.settings.set(key, undefined);
      }
      window.location.reload();
    });
  }, []);

  const s = settings; // shorthand

  return (
    <div className="flex h-full">
      {/* Left sidebar nav */}
      <div className="w-48 border-r border-nock-border bg-nock-bg shrink-0 flex flex-col">
        <div className="px-4 py-4 border-b border-nock-border">
          <h1 className="font-display font-bold text-lg nock-gradient-text">Settings</h1>
        </div>
        <nav className="flex-1 overflow-y-auto py-2">
          {SECTIONS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setActiveSection(id)}
              className={`w-full flex items-center gap-2.5 px-4 py-2 text-left transition-colors ${
                activeSection === id
                  ? 'bg-nock-card text-nock-text border-r-2 border-nock-accent-blue'
                  : 'text-nock-text-dim hover:text-nock-text hover:bg-nock-card/40'
              }`}
            >
              <Icon size={14} />
              <span className="text-[12px] font-medium">{label}</span>
            </button>
          ))}
        </nav>
        {saved && (
          <div className="px-4 py-2 border-t border-nock-border">
            <span className="font-mono text-[10px] text-nock-green tracking-wider uppercase animate-fade-in">
              Saved
            </span>
          </div>
        )}
      </div>

      {/* Right content */}
      <div className="flex-1 overflow-y-auto px-8 py-6">
        <div className="max-w-2xl">

          {/* GENERAL */}
          {activeSection === 'general' && (
            <SettingsSection title="General">
              <Field label="Theme">
                <Select value={s.theme || 'dark'} onChange={v => updateSetting('theme', v)}
                  options={[{ value: 'dark', label: 'Dark' }, { value: 'light', label: 'Light (coming soon)', disabled: true }, { value: 'system', label: 'System (coming soon)', disabled: true }]} />
              </Field>
              <Field label="Start Minimized to Tray">
                <Toggle checked={!!s.startMinimized} onChange={v => updateSetting('startMinimized', v)} />
              </Field>
              <Field label="Always on Top">
                <Toggle checked={!!s.alwaysOnTop} onChange={v => updateSetting('alwaysOnTop', v)} />
              </Field>
              <Field label="Launch at Windows Startup">
                <Toggle checked={!!s.launchAtStartup} onChange={v => updateSetting('launchAtStartup', v)} />
              </Field>
              <Field label="Window Opacity">
                <Slider min={70} max={100} value={s.windowOpacity ?? 100} onChange={v => updateSetting('windowOpacity', v)} suffix="%" />
              </Field>
              <Field label="Dev Root Directories" description="One path per line. Git repos in these folders auto-appear on the dashboard.">
                <textarea rows={3} value={devRootsDraft} onChange={e => setDevRootsDraft(e.target.value)}
                  onBlur={() => commitListSetting('devRoots', devRootsDraft)}
                  className="settings-input resize-none font-mono" placeholder="C:\Dev" />
              </Field>
              <Field label="Hidden Projects" description="Folder names to hide (case-insensitive, one per line).">
                <textarea rows={3} value={skipListDraft} onChange={e => setSkipListDraft(e.target.value)}
                  onBlur={() => commitListSetting('projectSkipList', skipListDraft)}
                  className="settings-input resize-none font-mono" placeholder="Gym-App" />
              </Field>
            </SettingsSection>
          )}

          {/* AI / MODELS */}
          {activeSection === 'ai' && (
            <SettingsSection title="AI / Models">
              <Field label="Ollama Endpoint URL">
                <input type="text" value={s.ollamaUrl || ''} onChange={e => updateSetting('ollamaUrl', e.target.value)}
                  className="settings-input font-mono" placeholder="http://localhost:11434" />
              </Field>
              <Field label="Default Model">
                <Select value={s.defaultModel || 'qwen3.5:9b'} onChange={v => updateSetting('defaultModel', v)}
                  options={ollamaModels.length > 0
                    ? ollamaModels.map(m => ({ value: typeof m === 'string' ? m : m.name, label: typeof m === 'string' ? m : m.name }))
                    : [{ value: 'qwen3.5:9b', label: 'qwen3.5:9b' }]} />
              </Field>
              <Field label="System Prompt">
                <textarea rows={4} value={systemPromptDraft} onChange={e => setSystemPromptDraft(e.target.value)}
                  onBlur={() => updateSetting('systemPrompt', systemPromptDraft)}
                  className="settings-input resize-none" placeholder="You are a helpful coding assistant..." />
              </Field>
              <Field label="Temperature">
                <Slider min={0} max={200} value={Math.round((s.temperature ?? 0.7) * 100)} onChange={v => updateSetting('temperature', v / 100)} displayValue={(s.temperature ?? 0.7).toFixed(1)} />
              </Field>
              <Field label="Max Tokens">
                <input type="number" value={s.maxTokens ?? 4096} onChange={e => updateSetting('maxTokens', parseInt(e.target.value) || 4096)}
                  className="settings-input font-mono w-32" min={256} max={131072} />
              </Field>
              <Field label="Show Thinking / Reasoning" description="For models that support it (e.g., Qwen 3.5)">
                <Toggle checked={!!s.showThinking} onChange={v => updateSetting('showThinking', v)} />
              </Field>
              <Field label="Claude Code Binary Path" description="Leave empty for auto-detection.">
                <input type="text" value={s.claudeCodePath || ''} onChange={e => updateSetting('claudeCodePath', e.target.value)}
                  className="settings-input font-mono" placeholder="Auto-detect" />
              </Field>
            </SettingsSection>
          )}

          {/* TERMINAL */}
          {activeSection === 'terminal' && (
            <SettingsSection title="Terminal">
              <Field label="Default Shell">
                <Select value={s.defaultShell || ''} onChange={v => updateSetting('defaultShell', v)}
                  options={[{ value: '', label: 'Auto-detect' }, ...shells.map(sh => ({ value: sh.path, label: sh.name }))]} />
              </Field>
              <Field label="Shell Arguments" description="e.g., -NoProfile for PowerShell">
                <input type="text" value={s.shellArgs || ''} onChange={e => updateSetting('shellArgs', e.target.value)}
                  className="settings-input font-mono" placeholder="-NoLogo" />
              </Field>
              <Field label="Font Family">
                <Select value={s.terminalFontFamily || FONT_OPTIONS[0].value} onChange={v => updateSetting('terminalFontFamily', v)} options={FONT_OPTIONS} />
              </Field>
              <Field label="Font Size">
                <Slider min={10} max={24} value={s.terminalFontSize ?? 16} onChange={v => updateSetting('terminalFontSize', v)} suffix="px" />
              </Field>
              <Field label="Scrollback Buffer Size">
                <input type="number" value={s.scrollbackSize ?? 5000} onChange={e => updateSetting('scrollbackSize', parseInt(e.target.value) || 5000)}
                  className="settings-input font-mono w-32" min={100} max={100000} />
              </Field>
              <Field label="Cursor Style">
                <Select value={s.cursorStyle || 'block'} onChange={v => updateSetting('cursorStyle', v)} options={CURSOR_OPTIONS} />
              </Field>
              <Field label="Cursor Blink">
                <Toggle checked={s.cursorBlink !== false} onChange={v => updateSetting('cursorBlink', v)} />
              </Field>
              <Field label="Bell Sound">
                <Toggle checked={!!s.bellSound} onChange={v => updateSetting('bellSound', v)} />
              </Field>
              <Field label="Copy on Select">
                <Toggle checked={!!s.copyOnSelect} onChange={v => updateSetting('copyOnSelect', v)} />
              </Field>
              <Field label="Right-click Paste">
                <Toggle checked={s.rightClickPaste !== false} onChange={v => updateSetting('rightClickPaste', v)} />
              </Field>
            </SettingsSection>
          )}

          {/* EDITOR */}
          {activeSection === 'editor' && (
            <SettingsSection title="Editor">
              <Field label="Font Family">
                <Select value={s.editorFontFamily || FONT_OPTIONS[0].value} onChange={v => updateSetting('editorFontFamily', v)} options={FONT_OPTIONS} />
              </Field>
              <Field label="Font Size">
                <Slider min={10} max={24} value={s.editorFontSize ?? 15} onChange={v => updateSetting('editorFontSize', v)} suffix="px" />
              </Field>
              <Field label="Minimap">
                <Toggle checked={!!s.editorMinimap} onChange={v => updateSetting('editorMinimap', v)} />
              </Field>
              <Field label="Word Wrap">
                <Toggle checked={!!s.editorWordWrap} onChange={v => updateSetting('editorWordWrap', v)} />
              </Field>
            </SettingsSection>
          )}

          {/* FILE TREE */}
          {activeSection === 'filetree' && (
            <SettingsSection title="File Tree">
              <Field label="Open File Tree by Default">
                <Toggle checked={s.fileTreeOpen !== false} onChange={v => updateSetting('fileTreeOpen', v)} />
              </Field>
              <Field label="Show Dotfiles">
                <Toggle checked={!!s.showDotfiles} onChange={v => updateSetting('showDotfiles', v)} />
              </Field>
            </SettingsSection>
          )}

          {/* NOTIFICATIONS */}
          {activeSection === 'notifications' && (
            <SettingsSection title="Notifications">
              <Field label="Enable Desktop Notifications">
                <Toggle checked={s.desktopNotifications !== false} onChange={v => updateSetting('desktopNotifications', v)} />
              </Field>
              <Field label="Notification Sound">
                <Toggle checked={!!s.notificationSound} onChange={v => updateSetting('notificationSound', v)} />
              </Field>
              <div className="border-t border-nock-border pt-4 mt-4">
                <p className="font-mono text-[10px] text-nock-text-muted uppercase tracking-widest mb-3">Notify on</p>
                <Field label="PR Merged"><Toggle checked={s.notifyPrMerged !== false} onChange={v => updateSetting('notifyPrMerged', v)} /></Field>
                <Field label="Build Complete"><Toggle checked={s.notifyBuildComplete !== false} onChange={v => updateSetting('notifyBuildComplete', v)} /></Field>
                <Field label="Session Ended"><Toggle checked={s.notifySessionEnded !== false} onChange={v => updateSetting('notifySessionEnded', v)} /></Field>
                <Field label="Fence Event"><Toggle checked={!!s.notifyFenceEvent} onChange={v => updateSetting('notifyFenceEvent', v)} /></Field>
              </div>
            </SettingsSection>
          )}

          {/* TELEGRAM */}
          {activeSection === 'telegram' && (
            <SettingsSection title="Telegram">
              <Field label="Enable Telegram Notifications">
                <Toggle checked={!!s.telegramEnabled} onChange={v => updateSetting('telegramEnabled', v)} />
              </Field>
              <Field label="Bot Token">
                <input type="password" value={s.telegramBotToken || ''} onChange={e => updateSetting('telegramBotToken', e.target.value)}
                  className="settings-input font-mono" placeholder="123456:ABC-DEF..." />
              </Field>
              <Field label="Chat ID">
                <input type="text" value={s.telegramChatId || ''} onChange={e => updateSetting('telegramChatId', e.target.value)}
                  className="settings-input font-mono" placeholder="-1001234567890" />
              </Field>
              <Field label="Test Notification">
                <button onClick={() => window.nockTerminal.telegram?.test()} className="settings-button">
                  Send Test
                </button>
              </Field>
              <div className="border-t border-nock-border pt-4 mt-4">
                <p className="font-mono text-[10px] text-nock-text-muted uppercase tracking-widest mb-3">Quiet Hours</p>
                <div className="flex items-center gap-3">
                  <Field label="Start">
                    <input type="time" value={s.telegramQuietStart || '22:00'} onChange={e => updateSetting('telegramQuietStart', e.target.value)}
                      className="settings-input font-mono w-28" />
                  </Field>
                  <span className="text-nock-text-muted mt-5">to</span>
                  <Field label="End">
                    <input type="time" value={s.telegramQuietEnd || '07:00'} onChange={e => updateSetting('telegramQuietEnd', e.target.value)}
                      className="settings-input font-mono w-28" />
                  </Field>
                </div>
              </div>
              <div className="border-t border-nock-border pt-4 mt-4">
                <p className="font-mono text-[10px] text-nock-text-muted uppercase tracking-widest mb-3">Notify on</p>
                <Field label="PR Merged"><Toggle checked={s.telegramNotifyPrMerged !== false} onChange={v => updateSetting('telegramNotifyPrMerged', v)} /></Field>
                <Field label="Build Complete"><Toggle checked={s.telegramNotifyBuildComplete !== false} onChange={v => updateSetting('telegramNotifyBuildComplete', v)} /></Field>
                <Field label="Session Ended"><Toggle checked={s.telegramNotifySessionEnded !== false} onChange={v => updateSetting('telegramNotifySessionEnded', v)} /></Field>
                <Field label="Fence Event"><Toggle checked={!!s.telegramNotifyFenceEvent} onChange={v => updateSetting('telegramNotifyFenceEvent', v)} /></Field>
              </div>
            </SettingsSection>
          )}

          {/* SHORTCUTS */}
          {activeSection === 'shortcuts' && (
            <SettingsSection title="Keyboard Shortcuts">
              <div className="space-y-1.5">
                {[
                  ['Ctrl+T', 'New terminal tab'],
                  ['Ctrl+W', 'Close editor tab or split'],
                  ['Ctrl+B', 'Toggle sidebar'],
                  ['Ctrl+D', 'Dashboard'],
                  ['Ctrl+P', 'Quick file finder'],
                  ['Ctrl+1-9', 'Switch to tab N'],
                  ['Ctrl+Tab / Ctrl+Shift+Tab', 'Next / previous tab'],
                  ['Ctrl+Shift+A', 'Toggle AI chat panel'],
                  ['Ctrl+Shift+D', 'Split terminal'],
                  ['Ctrl+Shift+T', 'Toggle window (global)'],
                  ['Ctrl+S', 'Save file (editor)'],
                  ['Ctrl+`', 'Focus terminal'],
                  ['F11', 'Fullscreen'],
                ].map(([keys, action]) => (
                  <div key={keys} className="flex items-center justify-between py-1.5">
                    <span className="text-xs text-nock-text-dim">{action}</span>
                    <kbd className="font-mono text-[10px] bg-nock-card border border-nock-border rounded px-2 py-0.5 text-nock-text">{keys}</kbd>
                  </div>
                ))}
              </div>
            </SettingsSection>
          )}

          {/* DATA */}
          {activeSection === 'data' && (
            <SettingsSection title="Data">
              <div className="space-y-3">
                <button onClick={exportSettings} className="settings-button flex items-center gap-2">
                  <Download size={14} /> Export Settings (JSON)
                </button>
                <button onClick={importSettings} className="settings-button flex items-center gap-2">
                  <Upload size={14} /> Import Settings (JSON)
                </button>
                <button onClick={resetSettings} className="settings-button-danger flex items-center gap-2">
                  <RotateCcw size={14} /> Reset All to Defaults
                </button>
              </div>
            </SettingsSection>
          )}

          {/* ABOUT */}
          {activeSection === 'about' && (
            <SettingsSection title="About">
              <div className="space-y-3">
                <InfoRow label="App Version" value={appVersion} />
                <InfoRow label="Ollama Version" value={ollamaVersion} />
                <InfoRow label="Models Installed" value={ollamaModels.length > 0 ? ollamaModels.map(m => typeof m === 'string' ? m : m.name).join(', ') : 'None detected'} />
                <div className="border-t border-nock-border pt-3 mt-3 space-y-2">
                  <button onClick={() => window.nockTerminal.shell.openExternal('https://github.com/kkwills13/nock-command-center')}
                    className="settings-button flex items-center gap-2">
                    <ExternalLink size={14} /> GitHub Repository
                  </button>
                  <button onClick={() => window.nockTerminal.shell.openExternal('https://nocktechnologies.io')}
                    className="settings-button flex items-center gap-2">
                    <ExternalLink size={14} /> Nock Technologies
                  </button>
                </div>
              </div>
            </SettingsSection>
          )}

        </div>
      </div>
    </div>
  );
}

// --- Reusable sub-components ---

function SettingsSection({ title, children }) {
  return (
    <div>
      <h2 className="font-display font-semibold text-xl text-nock-text mb-6">{title}</h2>
      <div className="space-y-5">{children}</div>
    </div>
  );
}

function Field({ label, description, children }) {
  return (
    <div className="space-y-1">
      <label className="block font-mono text-[11px] font-medium text-nock-text tracking-wide">{label}</label>
      {description && <p className="text-[10px] text-nock-text-muted font-mono">{description}</p>}
      {children}
    </div>
  );
}

function Toggle({ checked, onChange }) {
  return (
    <button
      onClick={() => onChange(!checked)}
      className={`relative w-9 h-5 rounded-full transition-colors ${checked ? 'bg-nock-accent-blue' : 'bg-nock-border'}`}
    >
      <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${checked ? 'left-[18px]' : 'left-0.5'}`} />
    </button>
  );
}

function Slider({ min, max, value, onChange, suffix, displayValue }) {
  return (
    <div className="flex items-center gap-4">
      <input type="range" min={min} max={max} value={value} onChange={e => onChange(parseInt(e.target.value))}
        className="flex-1 accent-[#3B6FD4]" />
      <span className="font-mono text-sm text-nock-text tabular-nums w-14 text-right">
        {displayValue ?? value}{suffix || ''}
      </span>
    </div>
  );
}

function Select({ value, onChange, options }) {
  return (
    <select value={value} onChange={e => onChange(e.target.value)}
      className="settings-input font-mono appearance-none">
      {options.map(o => (
        <option key={o.value} value={o.value} disabled={o.disabled}>{o.label}</option>
      ))}
    </select>
  );
}

function InfoRow({ label, value }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-xs text-nock-text-dim">{label}</span>
      <span className="font-mono text-xs text-nock-text">{value}</span>
    </div>
  );
}
```

- [ ] **Step 5: Add settings CSS classes to index.css**

Add these utility classes to `terminal-electron/src/index.css` (after the existing Tailwind directives):

```css
.settings-input {
  @apply w-full bg-nock-card border border-nock-border rounded px-3 py-2 text-sm text-nock-text focus:outline-none focus:border-nock-accent-blue transition-colors;
}
.settings-button {
  @apply px-4 py-2 bg-nock-card border border-nock-border rounded text-sm text-nock-text hover:bg-nock-card-hover hover:border-nock-border-bright transition-colors;
}
.settings-button-danger {
  @apply px-4 py-2 bg-nock-card border border-red-500/30 rounded text-sm text-nock-red hover:bg-red-500/10 transition-colors;
}
```

- [ ] **Step 6: Verify settings page renders**

```bash
cd terminal-electron
npm start
```

Navigate to Settings. Verify: left sidebar with 10 sections, clicking each shows correct content, changing a value shows "Saved" indicator, changes persist after reload.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat: expand settings page with full sections and auto-persist"
```

---

## Task 3: Status Bar

**Files:**
- Create: `terminal-electron/src/components/StatusBar.jsx`
- Modify: `terminal-electron/src/App.jsx`

- [ ] **Step 1: Create StatusBar.jsx**

Create `terminal-electron/src/components/StatusBar.jsx`:

```jsx
import React, { useState, useEffect } from 'react';
import { GitBranch, Monitor, Wifi, WifiOff, Clock } from 'lucide-react';

export default function StatusBar({ activeTab, sessions, ollamaStatus, processStatus }) {
  const [time, setTime] = useState(new Date());

  useEffect(() => {
    const interval = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(interval);
  }, []);

  const activeSessions = sessions.filter(s => s.status === 'active').length;
  const projectName = activeTab?.title || 'No project';
  const branch = activeTab?.branch || '';

  const proc = activeTab ? processStatus[activeTab.id] : null;
  const contextPct = proc?.contextPercent;

  const timeStr = time.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

  return (
    <div className="h-6 bg-nock-bg-elevated border-t border-nock-border flex items-center px-3 shrink-0 select-none">
      {/* Left: project + branch */}
      <div className="flex items-center gap-2 flex-1 min-w-0">
        <span className="font-mono text-[10px] text-nock-text truncate">{projectName}</span>
        {branch && (
          <span className="flex items-center gap-1 font-mono text-[10px] text-nock-accent-blue truncate">
            <GitBranch size={10} />
            {branch}
          </span>
        )}
      </div>

      {/* Center: sessions + ollama */}
      <div className="flex items-center gap-3">
        <span className="flex items-center gap-1 font-mono text-[10px] text-nock-text-dim">
          <Monitor size={10} />
          {activeSessions} active
        </span>
        <span className="flex items-center gap-1 font-mono text-[10px]">
          {ollamaStatus ? (
            <>
              <Wifi size={10} className="text-nock-green" />
              <span className="text-nock-green">Ollama</span>
            </>
          ) : (
            <>
              <WifiOff size={10} className="text-nock-red" />
              <span className="text-nock-red">Ollama</span>
            </>
          )}
        </span>
      </div>

      {/* Right: context %, clock */}
      <div className="flex items-center gap-3 flex-1 justify-end min-w-0">
        {contextPct != null && (
          <span className={`font-mono text-[10px] ${contextPct > 80 ? 'text-nock-red' : contextPct > 50 ? 'text-nock-yellow' : 'text-nock-text-dim'}`}>
            CTX {contextPct}%
          </span>
        )}
        <span className="flex items-center gap-1 font-mono text-[10px] text-nock-text-muted">
          <Clock size={10} />
          {timeStr}
        </span>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Add ollamaStatus state and wire StatusBar into App.jsx**

In `terminal-electron/src/App.jsx`:

1. Add import at top (after Settings import):
```jsx
import StatusBar from './components/StatusBar';
```

2. Add ollamaStatus state (after line 22):
```jsx
const [ollamaStatus, setOllamaStatus] = useState(false);
```

3. Add Ollama polling effect (after the existing refreshPorts effect, around line 51):
```jsx
useEffect(() => {
  const check = async () => {
    try {
      const status = await window.nockTerminal.ai.ollama.status();
      setOllamaStatus(status.connected);
    } catch {
      setOllamaStatus(false);
    }
  };
  check();
  const interval = setInterval(check, 30000);
  return () => clearInterval(interval);
}, []);
```

4. Add StatusBar just before the closing `</div>` of the root div (before the chat toggle button, around line 433):
```jsx
      <StatusBar
        activeTab={activeTab}
        sessions={sessions}
        ollamaStatus={ollamaStatus}
        processStatus={processStatus}
      />
```

- [ ] **Step 3: Verify status bar renders**

```bash
cd terminal-electron
npm start
```

Verify: bottom bar shows across all views (dashboard, terminal, settings), shows project name, branch, Ollama status, clock.

- [ ] **Step 4: Commit**

```bash
git add src/components/StatusBar.jsx src/App.jsx
git commit -m "feat: add persistent status bar with project, session, and Ollama status"
```

---

## Task 4: Dynamic Model Selector

**Files:**
- Modify: `terminal-electron/electron/ollama-client.js`
- Modify: `terminal-electron/src/components/AIChatPanel.jsx`

- [ ] **Step 1: Enhance listModels() in ollama-client.js**

Replace the `listModels()` method in `terminal-electron/electron/ollama-client.js` (lines 22-29):

```javascript
  async listModels() {
    try {
      const response = await this._fetch('/api/tags', 'GET');
      return (response.models || []).map(m => ({
        name: m.name,
        size: m.size,
        parameterSize: m.details?.parameter_size || '',
        quantization: m.details?.quantization_level || '',
        family: m.details?.family || '',
        contextLength: m.details?.context_length || null,
      }));
    } catch {
      return [];
    }
  }
```

- [ ] **Step 2: Rewrite AIChatPanel.jsx model selector**

Replace the entire content of `terminal-electron/src/components/AIChatPanel.jsx`:

```jsx
import React, { useState, useRef, useEffect, useCallback } from 'react';
import { ChevronDown, RefreshCw, ExternalLink, Terminal } from 'lucide-react';
import ChatMessage from './ChatMessage';

function formatSize(bytes) {
  if (!bytes) return '';
  const gb = bytes / (1024 * 1024 * 1024);
  return gb >= 1 ? `${gb.toFixed(1)}GB` : `${(bytes / (1024 * 1024)).toFixed(0)}MB`;
}

export default function AIChatPanel({ onClose, activeSession, onOpenTerminalWithClaude }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [selectedModel, setSelectedModel] = useState(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [ollamaStatus, setOllamaStatus] = useState(null);
  const [ollamaModels, setOllamaModels] = useState([]);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [hasClaudeCode, setHasClaudeCode] = useState(false);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  const dropdownRef = useRef(null);

  // Load saved model preference
  useEffect(() => {
    window.nockTerminal.settings.get('defaultModel').then(saved => {
      setSelectedModel(saved || 'qwen3.5:9b');
    });
  }, []);

  // Check Ollama status and load models
  const refreshModels = useCallback(async () => {
    try {
      const status = await window.nockTerminal.ai.ollama.status();
      setOllamaStatus(status.connected);
      if (status.connected) {
        const models = await window.nockTerminal.ai.ollama.models();
        setOllamaModels(models);
      } else {
        setOllamaModels([]);
      }
    } catch {
      setOllamaStatus(false);
      setOllamaModels([]);
    }
  }, []);

  useEffect(() => {
    refreshModels();
    const interval = setInterval(refreshModels, 30000);
    return () => clearInterval(interval);
  }, [refreshModels]);

  // Detect Claude Code
  useEffect(() => {
    window.nockTerminal.settings.get('claudeCodePath').then(path => {
      // If path is set or we can detect it, show Kit
      setHasClaudeCode(true); // Claude Code is always available on this machine
    });
  }, []);

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    const cleanup = window.nockTerminal.ai.onStream((chunk) => {
      setMessages(prev => {
        const last = prev[prev.length - 1];
        if (last && last.role === 'assistant' && last.streaming) {
          return [...prev.slice(0, -1), { ...last, content: last.content + chunk }];
        }
        return prev;
      });
    });
    return cleanup;
  }, []);

  const selectModel = useCallback((modelId) => {
    if (modelId === 'kit') {
      // Open Claude Code in a new terminal tab
      onOpenTerminalWithClaude?.(activeSession?.cwd);
      setDropdownOpen(false);
      return;
    }
    if (modelId === 'mara') {
      window.nockTerminal.shell.openExternal('https://claude.ai');
      setDropdownOpen(false);
      return;
    }
    setSelectedModel(modelId);
    window.nockTerminal.settings.set('defaultModel', modelId);
    setDropdownOpen(false);
  }, [activeSession, onOpenTerminalWithClaude]);

  const sendMessage = useCallback(async () => {
    const text = input.trim();
    if (!text || isStreaming || !selectedModel) return;

    const userMsg = { role: 'user', content: text };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setIsStreaming(true);

    const modelObj = ollamaModels.find(m => m.name === selectedModel);
    const displayName = modelObj?.name || selectedModel;
    setMessages(prev => [...prev, { role: 'assistant', content: '', streaming: true, model: displayName }]);

    try {
      const chatMessages = [...messages, userMsg].map(m => ({ role: m.role, content: m.content }));
      await window.nockTerminal.ai.ollama.chat(selectedModel, chatMessages);
    } catch (err) {
      setMessages(prev => {
        const last = prev[prev.length - 1];
        if (last && last.streaming) {
          return [...prev.slice(0, -1), { ...last, content: last.content || `Error: ${err.message}`, streaming: false, error: true }];
        }
        return prev;
      });
    }

    setMessages(prev => {
      const last = prev[prev.length - 1];
      if (last && last.streaming) return [...prev.slice(0, -1), { ...last, streaming: false }];
      return prev;
    });
    setIsStreaming(false);
  }, [input, isStreaming, selectedModel, messages, ollamaModels]);

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      sendMessage();
    }
  };

  const currentModelDisplay = ollamaModels.find(m => m.name === selectedModel)?.name || selectedModel || 'Select model';

  return (
    <div className="w-[400px] bg-nock-bg border-l border-nock-border flex flex-col shrink-0 h-full">
      {/* Header */}
      <div className="px-4 py-3 border-b border-nock-border shrink-0 relative">
        <div className="absolute bottom-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-nock-accent-purple/30 to-transparent" />
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="font-mono text-[9px] text-nock-accent-cyan tracking-widest uppercase">// 02</span>
            <span className="font-display font-semibold text-[13px] nock-gradient-text tracking-wide">AI Chat</span>
            <span
              className={`w-1.5 h-1.5 rounded-full ${
                ollamaStatus === true ? 'bg-nock-green shadow-glow-green animate-pulse-glow' :
                ollamaStatus === false ? 'bg-nock-red' :
                'bg-nock-yellow'
              }`}
              title={ollamaStatus ? 'Ollama connected' : 'Ollama disconnected'}
            />
          </div>
          <button onClick={onClose} className="text-nock-text-muted hover:text-nock-text transition-colors" title="Close (Ctrl+Shift+A)">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>

      {/* Model selector dropdown */}
      <div className="px-3 py-2.5 border-b border-nock-border shrink-0" ref={dropdownRef}>
        <div className="relative">
          <button
            onClick={() => setDropdownOpen(prev => !prev)}
            className="w-full flex items-center justify-between px-3 py-2 bg-nock-card border border-nock-border rounded-md text-sm text-nock-text hover:border-nock-accent-blue transition-colors"
          >
            <span className="font-mono text-[11px] truncate">{currentModelDisplay}</span>
            <ChevronDown size={14} className={`text-nock-text-muted transition-transform ${dropdownOpen ? 'rotate-180' : ''}`} />
          </button>

          {dropdownOpen && (
            <div className="absolute top-full left-0 right-0 mt-1 bg-nock-card border border-nock-border rounded-lg shadow-2xl z-50 max-h-64 overflow-y-auto">
              {/* Ollama models */}
              {ollamaStatus === false && (
                <div className="px-3 py-3 text-center">
                  <p className="text-[11px] text-nock-red mb-2">Ollama offline</p>
                  <button onClick={refreshModels} className="flex items-center gap-1.5 mx-auto text-[10px] text-nock-accent-blue hover:underline">
                    <RefreshCw size={10} /> Retry
                  </button>
                </div>
              )}
              {ollamaModels.map(model => (
                <button
                  key={model.name}
                  onClick={() => selectModel(model.name)}
                  className={`w-full text-left px-3 py-2 hover:bg-nock-border-bright/30 transition-colors ${
                    selectedModel === model.name ? 'bg-nock-accent-blue/10 border-l-2 border-nock-accent-blue' : ''
                  }`}
                >
                  <div className="font-mono text-[11px] text-nock-text">{model.name}</div>
                  <div className="font-mono text-[9px] text-nock-text-muted">
                    {formatSize(model.size)}
                    {model.parameterSize ? ` · ${model.parameterSize}` : ''}
                    {model.family ? ` · ${model.family}` : ''}
                  </div>
                </button>
              ))}

              {/* Divider */}
              {(hasClaudeCode || true) && ollamaModels.length > 0 && (
                <div className="border-t border-nock-border my-1" />
              )}

              {/* Kit — Claude Code */}
              {hasClaudeCode && (
                <button
                  onClick={() => selectModel('kit')}
                  className="w-full text-left px-3 py-2 hover:bg-nock-border-bright/30 transition-colors"
                >
                  <div className="flex items-center gap-1.5">
                    <Terminal size={11} className="text-nock-accent-purple" />
                    <span className="font-mono text-[11px] text-nock-text">Kit (Claude Code)</span>
                  </div>
                  <div className="font-mono text-[9px] text-nock-text-muted">Opens terminal with claude CLI</div>
                </button>
              )}

              {/* Mara — claude.ai */}
              <button
                onClick={() => selectModel('mara')}
                className="w-full text-left px-3 py-2 hover:bg-nock-border-bright/30 transition-colors"
              >
                <div className="flex items-center gap-1.5">
                  <ExternalLink size={11} className="text-nock-accent-cyan" />
                  <span className="font-mono text-[11px] text-nock-text">Mara (claude.ai)</span>
                </div>
                <div className="font-mono text-[9px] text-nock-text-muted">Opens Claude chat in browser</div>
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {messages.length === 0 && (
          <div className="text-center mt-10">
            <div className="inline-block mb-3 p-3 rounded-full bg-nock-card border border-nock-border">
              <img src="./nock-logo.png" alt="" className="w-8 h-8 opacity-60" />
            </div>
            <p className="font-display text-[13px] text-nock-text mb-1">Ready for instructions</p>
            <p className="font-mono text-[9px] text-nock-text-muted tracking-wider uppercase">
              Currently: {currentModelDisplay}
            </p>
          </div>
        )}
        {messages.map((msg, i) => <ChatMessage key={i} message={msg} />)}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="px-3 py-3 border-t border-nock-border shrink-0 bg-nock-bg-elevated/30">
        <div className="relative">
          <textarea ref={inputRef} value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={handleKeyDown}
            placeholder="Ask anything…" rows={3}
            className="w-full bg-nock-card border border-nock-border rounded-lg px-3 py-2.5 text-sm text-nock-text placeholder-nock-text-muted resize-none focus:outline-none focus:border-nock-accent-blue focus:shadow-glow-blue transition-shadow"
            disabled={isStreaming} />
          <button onClick={sendMessage} disabled={!input.trim() || isStreaming}
            className="absolute bottom-2 right-2 h-7 px-3 rounded bg-gradient-to-br from-nock-accent-blue to-nock-accent-purple text-white font-mono text-[10px] font-semibold tracking-wider uppercase flex items-center gap-1.5 disabled:opacity-30 hover:shadow-glow-purple transition-shadow">
            {isStreaming ? (
              <>
                <svg className="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Streaming
              </>
            ) : (
              <>Send <kbd className="text-[8px] bg-white/15 border-white/10 px-1 py-0 text-white">^Enter</kbd></>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Wire up onOpenTerminalWithClaude in App.jsx**

Add callback in App.jsx (after `openNewTab` definition, around line 110):

```jsx
  const openTerminalWithClaude = useCallback((cwd) => {
    const tabId = `tab-${Date.now()}`;
    const newTab = {
      id: tabId,
      sessionId: null,
      title: 'Kit (Claude)',
      branch: null,
      status: 'active',
      cwd: cwd || 'C:\\Users\\kkwil',
      splitContent: null,
      splitRatio: 0.5,
      launchCommand: 'claude',
    };
    setTabs(prev => [...prev, newTab]);
    setActiveTabId(tabId);
    setView('terminal');
  }, []);
```

Update the AIChatPanel usage in App.jsx (around line 428):
```jsx
          <AIChatPanel
            onClose={() => setChatOpen(false)}
            activeSession={activeTab}
            onOpenTerminalWithClaude={openTerminalWithClaude}
          />
```

- [ ] **Step 4: Verify model selector**

```bash
cd terminal-electron
npm start
```

Open AI Chat panel. Verify: dropdown shows available Ollama models with size info, Kit and Mara appear at bottom, clicking Kit opens a terminal tab, clicking Mara opens browser.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: add dynamic model selector with Ollama API and Kit/Mara entries"
```

---

## Task 5: Telegram Notifier

**Files:**
- Create: `terminal-electron/electron/telegram-notifier.js`
- Modify: `terminal-electron/electron/main.js`
- Modify: `terminal-electron/electron/preload.js`

- [ ] **Step 1: Create telegram-notifier.js**

Create `terminal-electron/electron/telegram-notifier.js`:

```javascript
const https = require('https');

class TelegramNotifier {
  constructor(store) {
    this.store = store;
    this.lastSentAt = 0;
    this.MIN_INTERVAL_MS = 5000; // 5 second rate limit
  }

  isEnabled() {
    return this.store.get('telegramEnabled') &&
           this.store.get('telegramBotToken') &&
           this.store.get('telegramChatId');
  }

  isQuietHours() {
    const start = this.store.get('telegramQuietStart') || '22:00';
    const end = this.store.get('telegramQuietEnd') || '07:00';
    const now = new Date();
    const currentMinutes = now.getHours() * 60 + now.getMinutes();
    const [startH, startM] = start.split(':').map(Number);
    const [endH, endM] = end.split(':').map(Number);
    const startMinutes = startH * 60 + startM;
    const endMinutes = endH * 60 + endM;

    if (startMinutes <= endMinutes) {
      return currentMinutes >= startMinutes && currentMinutes < endMinutes;
    }
    // Overnight range (e.g., 22:00 to 07:00)
    return currentMinutes >= startMinutes || currentMinutes < endMinutes;
  }

  shouldNotify(eventType) {
    if (!this.isEnabled()) return false;
    if (this.isQuietHours()) return false;

    const map = {
      'pr_merged': 'telegramNotifyPrMerged',
      'build_complete': 'telegramNotifyBuildComplete',
      'session_ended': 'telegramNotifySessionEnded',
      'fence_event': 'telegramNotifyFenceEvent',
    };
    const settingKey = map[eventType];
    if (settingKey && !this.store.get(settingKey)) return false;

    // Rate limit
    const now = Date.now();
    if (now - this.lastSentAt < this.MIN_INTERVAL_MS) return false;

    return true;
  }

  async send(text) {
    const token = this.store.get('telegramBotToken');
    const chatId = this.store.get('telegramChatId');
    if (!token || !chatId) return { success: false, error: 'Missing bot token or chat ID' };

    this.lastSentAt = Date.now();

    return new Promise((resolve) => {
      const body = JSON.stringify({ chat_id: chatId, text, parse_mode: 'HTML' });
      const req = https.request({
        hostname: 'api.telegram.org',
        path: `/bot${token}/sendMessage`,
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) },
      }, (res) => {
        let data = '';
        res.on('data', chunk => data += chunk);
        res.on('end', () => {
          try {
            const parsed = JSON.parse(data);
            resolve({ success: parsed.ok, error: parsed.ok ? null : parsed.description });
          } catch {
            resolve({ success: false, error: 'Invalid response' });
          }
        });
      });

      req.on('error', (err) => {
        resolve({ success: false, error: err.message });
      });

      req.write(body);
      req.end();
    });
  }

  async notify(eventType, details) {
    if (!this.shouldNotify(eventType)) return;

    const timestamp = new Date().toLocaleString();
    const message = `🔔 <b>Nock Terminal</b>\n${eventType.replace(/_/g, ' ')}: ${details}\n<i>${timestamp}</i>`;
    const result = await this.send(message);
    if (!result.success) {
      console.error('Telegram notification failed:', result.error);
    }
    return result;
  }

  async test() {
    const timestamp = new Date().toLocaleString();
    return this.send(`🔔 <b>Nock Terminal</b> — Test notification\n<i>${timestamp}</i>`);
  }
}

module.exports = TelegramNotifier;
```

- [ ] **Step 2: Wire Telegram into main.js**

In `terminal-electron/electron/main.js`:

1. Add require at top (after ProcessDetector require, line 11):
```javascript
const TelegramNotifier = require('./telegram-notifier');
```

2. Add variable declaration (after processDetector declaration, line 44):
```javascript
let telegramNotifier = null;
```

3. Initialize in `initServices()` (after processDetector init, line 157):
```javascript
  telegramNotifier = new TelegramNotifier(store);
```

4. Add IPC handlers in `registerIPC()` (after the system handlers):
```javascript
  // Telegram
  ipcMain.handle('telegram:test', async () => {
    return telegramNotifier.test();
  });
  ipcMain.handle('telegram:notify', async (_, { eventType, details }) => {
    return telegramNotifier.notify(eventType, details);
  });
```

- [ ] **Step 3: Expose Telegram IPC in preload.js**

Add to `window.nockTerminal` in `terminal-electron/electron/preload.js` (after the system section):

```javascript
  // Telegram
  telegram: {
    test: () => ipcRenderer.invoke('telegram:test'),
    notify: (eventType, details) => ipcRenderer.invoke('telegram:notify', { eventType, details }),
  },
```

- [ ] **Step 4: Verify Telegram test button**

```bash
cd terminal-electron
npm start
```

Go to Settings → Telegram. Enter a bot token and chat ID. Click "Send Test". Verify the test message arrives on Telegram.

- [ ] **Step 5: Commit**

```bash
git add electron/telegram-notifier.js electron/main.js electron/preload.js
git commit -m "feat: add Telegram notification integration with quiet hours"
```

---

## Task 6: Project Profiles

**Files:**
- Create: `terminal-electron/electron/project-profiles.js`
- Create: `terminal-electron/src/components/ProjectSettingsModal.jsx`
- Modify: `terminal-electron/electron/main.js`
- Modify: `terminal-electron/electron/preload.js`
- Modify: `terminal-electron/src/components/Dashboard.jsx`

- [ ] **Step 1: Create project-profiles.js**

Create `terminal-electron/electron/project-profiles.js`:

```javascript
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

class ProjectProfiles {
  constructor() {
    this.dir = path.join(process.env.APPDATA || process.env.HOME, 'nock-terminal', 'projects');
    this._ensureDir();
  }

  _ensureDir() {
    try { fs.mkdirSync(this.dir, { recursive: true }); } catch {}
  }

  _hash(projectPath) {
    return crypto.createHash('md5').update(projectPath.toLowerCase()).digest('hex').slice(0, 12);
  }

  _filePath(projectPath) {
    return path.join(this.dir, `${this._hash(projectPath)}.json`);
  }

  get(projectPath) {
    try {
      const data = fs.readFileSync(this._filePath(projectPath), 'utf-8');
      return JSON.parse(data);
    } catch {
      return {
        projectPath,
        preferredModel: '',
        systemPrompt: '',
        defaultShell: '',
        envVars: '',
        claudeCommand: '',
        notes: '',
      };
    }
  }

  save(projectPath, profile) {
    this._ensureDir();
    const data = { ...profile, projectPath, updatedAt: new Date().toISOString() };
    fs.writeFileSync(this._filePath(projectPath), JSON.stringify(data, null, 2), 'utf-8');
    return { success: true };
  }

  delete(projectPath) {
    try {
      fs.unlinkSync(this._filePath(projectPath));
      return { success: true };
    } catch {
      return { success: false };
    }
  }

  list() {
    try {
      const files = fs.readdirSync(this.dir).filter(f => f.endsWith('.json'));
      return files.map(f => {
        try { return JSON.parse(fs.readFileSync(path.join(this.dir, f), 'utf-8')); } catch { return null; }
      }).filter(Boolean);
    } catch {
      return [];
    }
  }
}

module.exports = ProjectProfiles;
```

- [ ] **Step 2: Create ProjectSettingsModal.jsx**

Create `terminal-electron/src/components/ProjectSettingsModal.jsx`:

```jsx
import React, { useState, useEffect } from 'react';
import { X } from 'lucide-react';

export default function ProjectSettingsModal({ projectPath, projectName, onClose }) {
  const [profile, setProfile] = useState(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    window.nockTerminal.profiles.get(projectPath).then(setProfile);
  }, [projectPath]);

  const updateField = (key, value) => {
    const updated = { ...profile, [key]: value };
    setProfile(updated);
    window.nockTerminal.profiles.save(projectPath, updated);
    setSaved(true);
    setTimeout(() => setSaved(false), 1500);
  };

  if (!profile) return null;

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-nock-bg border border-nock-border rounded-xl w-[520px] max-h-[80vh] overflow-y-auto shadow-2xl" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-5 py-4 border-b border-nock-border">
          <div>
            <h2 className="font-display font-semibold text-base text-nock-text">{projectName}</h2>
            <p className="font-mono text-[10px] text-nock-text-muted truncate">{projectPath}</p>
          </div>
          <div className="flex items-center gap-2">
            {saved && <span className="font-mono text-[10px] text-nock-green animate-fade-in">Saved</span>}
            <button onClick={onClose} className="text-nock-text-muted hover:text-nock-text transition-colors">
              <X size={16} />
            </button>
          </div>
        </div>

        <div className="px-5 py-4 space-y-4">
          <ModalField label="Preferred AI Model" description="Override the default model for this project">
            <input type="text" value={profile.preferredModel || ''} onChange={e => updateField('preferredModel', e.target.value)}
              className="settings-input font-mono" placeholder="e.g., qwen3.5:9b" />
          </ModalField>

          <ModalField label="System Prompt" description="Custom system prompt for AI chat in this project">
            <textarea rows={3} value={profile.systemPrompt || ''} onChange={e => updateField('systemPrompt', e.target.value)}
              className="settings-input resize-none" placeholder="You are helping with..." />
          </ModalField>

          <ModalField label="Default Shell" description="Override terminal shell for this project">
            <input type="text" value={profile.defaultShell || ''} onChange={e => updateField('defaultShell', e.target.value)}
              className="settings-input font-mono" placeholder="Auto-detect" />
          </ModalField>

          <ModalField label="Environment Variables" description="KEY=VALUE, one per line. Set when opening terminal.">
            <textarea rows={3} value={profile.envVars || ''} onChange={e => updateField('envVars', e.target.value)}
              className="settings-input resize-none font-mono" placeholder="NODE_ENV=development" />
          </ModalField>

          <ModalField label="Claude Code Command" description="Custom command for Kit integration">
            <input type="text" value={profile.claudeCommand || ''} onChange={e => updateField('claudeCommand', e.target.value)}
              className="settings-input font-mono" placeholder="claude --dangerously-skip-permissions" />
          </ModalField>

          <ModalField label="Notes">
            <textarea rows={4} value={profile.notes || ''} onChange={e => updateField('notes', e.target.value)}
              className="settings-input resize-none" placeholder="Project context, reminders..." />
          </ModalField>
        </div>
      </div>
    </div>
  );
}

function ModalField({ label, description, children }) {
  return (
    <div>
      <label className="block font-mono text-[11px] font-medium text-nock-text tracking-wide mb-1">{label}</label>
      {description && <p className="text-[10px] text-nock-text-muted font-mono mb-1.5">{description}</p>}
      {children}
    </div>
  );
}
```

- [ ] **Step 3: Wire project profiles into main.js and preload.js**

In `terminal-electron/electron/main.js`:

1. Add require: `const ProjectProfiles = require('./project-profiles');`
2. Add variable: `let projectProfiles = null;`
3. In `initServices()`: `projectProfiles = new ProjectProfiles();`
4. Add IPC handlers:
```javascript
  // Project profiles
  ipcMain.handle('profiles:get', (_, projectPath) => projectProfiles.get(projectPath));
  ipcMain.handle('profiles:save', (_, { projectPath, profile }) => projectProfiles.save(projectPath, profile));
  ipcMain.handle('profiles:delete', (_, projectPath) => projectProfiles.delete(projectPath));
  ipcMain.handle('profiles:list', () => projectProfiles.list());
```

In `terminal-electron/electron/preload.js`, add:
```javascript
  // Project profiles
  profiles: {
    get: (projectPath) => ipcRenderer.invoke('profiles:get', projectPath),
    save: (projectPath, profile) => ipcRenderer.invoke('profiles:save', { projectPath, profile }),
    delete: (projectPath) => ipcRenderer.invoke('profiles:delete', projectPath),
    list: () => ipcRenderer.invoke('profiles:list'),
  },
```

- [ ] **Step 4: Add context menu to Dashboard project cards**

This will be completed in Task 9 (UI Polish) since it requires the reusable ContextMenu component. For now, the modal is accessible programmatically.

- [ ] **Step 5: Verify project profiles**

```bash
cd terminal-electron
npm start
```

Open dev tools console. Test: `await window.nockTerminal.profiles.save('C:\\Dev\\test', { preferredModel: 'qwen3.5:9b' })`. Then `await window.nockTerminal.profiles.get('C:\\Dev\\test')`.

- [ ] **Step 6: Commit**

```bash
git add electron/project-profiles.js src/components/ProjectSettingsModal.jsx electron/main.js electron/preload.js
git commit -m "feat: add project profiles with per-project settings"
```

---

## Task 7: Session History

**Files:**
- Create: `terminal-electron/electron/session-history.js`
- Create: `terminal-electron/src/components/SessionHistory.jsx`
- Modify: `terminal-electron/electron/terminal-manager.js`
- Modify: `terminal-electron/electron/main.js`
- Modify: `terminal-electron/electron/preload.js`
- Modify: `terminal-electron/src/components/Sidebar.jsx`

- [ ] **Step 1: Create session-history.js**

Create `terminal-electron/electron/session-history.js`:

```javascript
const fs = require('fs');
const path = require('path');

class SessionHistory {
  constructor(store) {
    this.store = store;
    this.dir = path.join(process.env.APPDATA || process.env.HOME, 'nock-terminal', 'sessions');
    this.activeSessions = new Map(); // tabId -> { metadata, buffer }
    this.MAX_SESSIONS = 100;
    this._ensureDir();
  }

  _ensureDir() {
    try { fs.mkdirSync(this.dir, { recursive: true }); } catch {}
  }

  startSession(tabId, metadata) {
    this.activeSessions.set(tabId, {
      metadata: {
        ...metadata,
        tabId,
        startTime: new Date().toISOString(),
        endTime: null,
        exitCode: null,
      },
      buffer: [],
      bufferSize: 0,
    });
  }

  appendOutput(tabId, data) {
    const session = this.activeSessions.get(tabId);
    if (!session) return;
    if (!this.store.get('autoCaptureSessions')) return;

    // Cap buffer at 2MB to prevent memory issues
    if (session.bufferSize > 2 * 1024 * 1024) return;
    session.buffer.push(data);
    session.bufferSize += data.length;
  }

  endSession(tabId, exitCode) {
    const session = this.activeSessions.get(tabId);
    if (!session) return;

    session.metadata.endTime = new Date().toISOString();
    session.metadata.exitCode = exitCode;

    const filename = `${session.metadata.startTime.replace(/[:.]/g, '-')}-${tabId}.json`;
    const record = {
      ...session.metadata,
      hasOutput: session.buffer.length > 0,
    };

    // Save metadata
    this._ensureDir();
    fs.writeFileSync(path.join(this.dir, filename), JSON.stringify(record, null, 2), 'utf-8');

    // Save output if captured
    if (session.buffer.length > 0) {
      const outputFile = filename.replace('.json', '.txt');
      fs.writeFileSync(path.join(this.dir, outputFile), session.buffer.join(''), 'utf-8');
    }

    this.activeSessions.delete(tabId);
    this._prune();
  }

  list() {
    try {
      const files = fs.readdirSync(this.dir)
        .filter(f => f.endsWith('.json'))
        .sort()
        .reverse();

      return files.slice(0, this.MAX_SESSIONS).map(f => {
        try { return JSON.parse(fs.readFileSync(path.join(this.dir, f), 'utf-8')); } catch { return null; }
      }).filter(Boolean);
    } catch {
      return [];
    }
  }

  getOutput(startTime, tabId) {
    const filename = `${startTime.replace(/[:.]/g, '-')}-${tabId}.txt`;
    try {
      return fs.readFileSync(path.join(this.dir, filename), 'utf-8');
    } catch {
      return null;
    }
  }

  _prune() {
    try {
      const files = fs.readdirSync(this.dir).filter(f => f.endsWith('.json')).sort().reverse();
      const toDelete = files.slice(this.MAX_SESSIONS);
      for (const f of toDelete) {
        try {
          fs.unlinkSync(path.join(this.dir, f));
          fs.unlinkSync(path.join(this.dir, f.replace('.json', '.txt')));
        } catch {}
      }
    } catch {}
  }
}

module.exports = SessionHistory;
```

- [ ] **Step 2: Add output capture to terminal-manager.js**

In `terminal-electron/electron/terminal-manager.js`, add a callback for output capture. Modify the `create()` method — after `ptyProcess.onData` (line 41), add an output capture hook:

```javascript
      ptyProcess.onData((data) => {
        this.emit('data', id, data);
        this.emit('output', id, data); // For session history capture
      });
```

Actually, the existing `data` event already serves this purpose. The session history module will listen to it. No changes needed to terminal-manager.js.

- [ ] **Step 3: Create SessionHistory.jsx**

Create `terminal-electron/src/components/SessionHistory.jsx`:

```jsx
import React, { useState, useEffect, useCallback } from 'react';
import { Clock, Terminal, Download, X } from 'lucide-react';

export default function SessionHistory() {
  const [sessions, setSessions] = useState([]);
  const [selectedSession, setSelectedSession] = useState(null);
  const [output, setOutput] = useState(null);

  useEffect(() => {
    window.nockTerminal.sessionHistory.list().then(setSessions);
  }, []);

  const viewOutput = useCallback(async (session) => {
    setSelectedSession(session);
    if (session.hasOutput) {
      const text = await window.nockTerminal.sessionHistory.getOutput(session.startTime, session.tabId);
      setOutput(text);
    } else {
      setOutput(null);
    }
  }, []);

  const exportOutput = useCallback(() => {
    if (!output || !selectedSession) return;
    const blob = new Blob([output], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `session-${selectedSession.startTime.replace(/[:.]/g, '-')}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  }, [output, selectedSession]);

  const formatTime = (iso) => {
    if (!iso) return '—';
    return new Date(iso).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  };

  const formatDuration = (start, end) => {
    if (!start || !end) return '—';
    const ms = new Date(end) - new Date(start);
    const mins = Math.floor(ms / 60000);
    const secs = Math.floor((ms % 60000) / 1000);
    return mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;
  };

  if (selectedSession) {
    return (
      <div className="flex flex-col h-full">
        <div className="px-3 py-2 border-b border-nock-border flex items-center justify-between shrink-0">
          <button onClick={() => { setSelectedSession(null); setOutput(null); }}
            className="text-nock-text-muted hover:text-nock-text transition-colors text-[11px] flex items-center gap-1">
            ← Back
          </button>
          {output && (
            <button onClick={exportOutput} className="text-nock-text-muted hover:text-nock-text transition-colors" title="Export">
              <Download size={12} />
            </button>
          )}
        </div>
        <div className="px-3 py-2 space-y-1 border-b border-nock-border shrink-0">
          <p className="font-mono text-[11px] text-nock-text">{selectedSession.project || selectedSession.tabId}</p>
          <p className="font-mono text-[9px] text-nock-text-muted">
            {formatTime(selectedSession.startTime)} · {formatDuration(selectedSession.startTime, selectedSession.endTime)}
            {selectedSession.exitCode != null && ` · exit ${selectedSession.exitCode}`}
          </p>
        </div>
        <div className="flex-1 overflow-auto p-3">
          {output ? (
            <pre className="font-mono text-[10px] text-nock-text-dim whitespace-pre-wrap break-all">{output}</pre>
          ) : (
            <p className="font-mono text-[10px] text-nock-text-muted text-center mt-4">No output captured</p>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-2 border-b border-nock-border shrink-0">
        <span className="font-mono text-[9px] text-nock-text-muted uppercase tracking-widest">// History</span>
      </div>
      <div className="flex-1 overflow-y-auto">
        {sessions.length === 0 && (
          <p className="font-mono text-[10px] text-nock-text-muted px-3 py-4 text-center">No sessions recorded</p>
        )}
        {sessions.map((s, i) => (
          <button key={i} onClick={() => viewOutput(s)}
            className="w-full text-left px-3 py-2 hover:bg-nock-card transition-colors border-b border-nock-border/50">
            <div className="flex items-center gap-2">
              <Terminal size={10} className="text-nock-text-muted shrink-0" />
              <span className="font-mono text-[10px] text-nock-text truncate">{s.project || s.tabId}</span>
              {s.hasOutput && <span className="w-1 h-1 rounded-full bg-nock-accent-cyan shrink-0" title="Has captured output" />}
            </div>
            <div className="font-mono text-[8px] text-nock-text-muted mt-0.5 pl-4">
              {formatTime(s.startTime)} · {formatDuration(s.startTime, s.endTime)}
              {s.exitCode != null && ` · exit ${s.exitCode}`}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Wire session history into main.js and preload.js**

In `terminal-electron/electron/main.js`:

1. Add require: `const SessionHistory = require('./session-history');`
2. Add variable: `let sessionHistory = null;`
3. In `initServices()`: `sessionHistory = new SessionHistory(store);`
4. In `wireTerminalEvents()`, add session capture:
```javascript
  terminalManager.on('data', (id, data) => {
    mainWindow?.webContents.send('terminal:data', { id, data });
    sessionHistory?.appendOutput(id, data);
  });
  terminalManager.on('exit', (id, code) => {
    mainWindow?.webContents.send('terminal:exit', { id, code });
    sessionHistory?.endSession(id, code);
  });
```

5. Add IPC handlers:
```javascript
  // Session history
  ipcMain.handle('sessionHistory:list', () => sessionHistory.list());
  ipcMain.handle('sessionHistory:getOutput', (_, { startTime, tabId }) => sessionHistory.getOutput(startTime, tabId));
  ipcMain.handle('sessionHistory:start', (_, { tabId, metadata }) => {
    sessionHistory.startSession(tabId, metadata);
    return { success: true };
  });
```

In `terminal-electron/electron/preload.js`, add:
```javascript
  // Session history
  sessionHistory: {
    list: () => ipcRenderer.invoke('sessionHistory:list'),
    getOutput: (startTime, tabId) => ipcRenderer.invoke('sessionHistory:getOutput', { startTime, tabId }),
    start: (tabId, metadata) => ipcRenderer.invoke('sessionHistory:start', { tabId, metadata }),
  },
```

- [ ] **Step 5: Add session start call in App.jsx**

In `terminal-electron/src/App.jsx`, in the `openTerminalTab` callback (around line 68), after creating the tab, add:

```javascript
    window.nockTerminal.sessionHistory.start(tabId, {
      project: session.name,
      shell: '',
      cwd: session.path,
    });
```

Do the same in `openNewTab` (around line 94):
```javascript
    window.nockTerminal.sessionHistory.start(tabId, {
      project: 'Terminal',
      shell: '',
      cwd: cwd || 'C:\\Users\\kkwil',
    });
```

- [ ] **Step 6: Add session history panel to Sidebar.jsx**

In `terminal-electron/src/components/Sidebar.jsx`, add import and panel. This will be a new sidebar section between ports and context monitor. Import at top:

```jsx
import SessionHistory from './SessionHistory';
```

Add a new section after the Ports section (after line 117):

```jsx
          {/* Session History */}
          <div className="border-t border-nock-border" style={{ maxHeight: '30%', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
            <SessionHistory />
          </div>
```

- [ ] **Step 7: Verify session history**

```bash
cd terminal-electron
npm start
```

Open a terminal tab. Type a few commands. Close the tab. Check the sidebar — session should appear in history. Click to view details.

- [ ] **Step 8: Commit**

```bash
git add electron/session-history.js src/components/SessionHistory.jsx electron/main.js electron/preload.js src/App.jsx src/components/Sidebar.jsx
git commit -m "feat: add session history and output capture"
```

---

## Task 8: Prompt Library

**Files:**
- Create: `terminal-electron/electron/prompt-store.js`
- Create: `terminal-electron/src/components/PromptLibrary.jsx`
- Modify: `terminal-electron/electron/main.js`
- Modify: `terminal-electron/electron/preload.js`
- Modify: `terminal-electron/src/components/Sidebar.jsx`

- [ ] **Step 1: Create prompt-store.js**

Create `terminal-electron/electron/prompt-store.js`:

```javascript
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

class PromptStore {
  constructor() {
    this.dir = path.join(process.env.APPDATA || process.env.HOME, 'nock-terminal', 'prompts');
    this._ensureDir();
  }

  _ensureDir() {
    try { fs.mkdirSync(this.dir, { recursive: true }); } catch {}
  }

  _id() {
    return crypto.randomBytes(6).toString('hex');
  }

  list() {
    try {
      const files = fs.readdirSync(this.dir).filter(f => f.endsWith('.md'));
      return files.map(f => {
        try {
          const content = fs.readFileSync(path.join(this.dir, f), 'utf-8');
          const { meta, body } = this._parseFrontmatter(content);
          return { id: f.replace('.md', ''), filename: f, ...meta, body };
        } catch { return null; }
      }).filter(Boolean).sort((a, b) => (b.updatedAt || '').localeCompare(a.updatedAt || ''));
    } catch {
      return [];
    }
  }

  get(id) {
    try {
      const content = fs.readFileSync(path.join(this.dir, `${id}.md`), 'utf-8');
      const { meta, body } = this._parseFrontmatter(content);
      return { id, ...meta, body };
    } catch {
      return null;
    }
  }

  save(id, { title, tags, body }) {
    this._ensureDir();
    const fileId = id || this._id();
    const frontmatter = `---\ntitle: ${title || 'Untitled'}\ntags: ${(tags || []).join(', ')}\nupdatedAt: ${new Date().toISOString()}\n---\n`;
    fs.writeFileSync(path.join(this.dir, `${fileId}.md`), frontmatter + (body || ''), 'utf-8');
    return { success: true, id: fileId };
  }

  delete(id) {
    try {
      fs.unlinkSync(path.join(this.dir, `${id}.md`));
      return { success: true };
    } catch {
      return { success: false };
    }
  }

  _parseFrontmatter(content) {
    const match = content.match(/^---\n([\s\S]*?)\n---\n([\s\S]*)$/);
    if (!match) return { meta: {}, body: content };
    const meta = {};
    for (const line of match[1].split('\n')) {
      const [key, ...rest] = line.split(':');
      if (key && rest.length) {
        const val = rest.join(':').trim();
        if (key.trim() === 'tags') {
          meta.tags = val.split(',').map(t => t.trim()).filter(Boolean);
        } else {
          meta[key.trim()] = val;
        }
      }
    }
    return { meta, body: match[2] };
  }
}

module.exports = PromptStore;
```

- [ ] **Step 2: Create PromptLibrary.jsx**

Create `terminal-electron/src/components/PromptLibrary.jsx`:

```jsx
import React, { useState, useEffect, useCallback } from 'react';
import { Plus, Play, Trash2, Tag } from 'lucide-react';

export default function PromptLibrary({ onExecutePrompt }) {
  const [prompts, setPrompts] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [editing, setEditing] = useState(null);

  const refresh = useCallback(async () => {
    const list = await window.nockTerminal.prompts.list();
    setPrompts(list);
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const createPrompt = useCallback(async () => {
    const result = await window.nockTerminal.prompts.save(null, {
      title: 'New Prompt',
      tags: [],
      body: '# New Prompt\n\nWrite your prompt here...',
    });
    await refresh();
    setSelectedId(result.id);
    setEditing(result.id);
  }, [refresh]);

  const deletePrompt = useCallback(async (id) => {
    await window.nockTerminal.prompts.delete(id);
    if (selectedId === id) setSelectedId(null);
    refresh();
  }, [selectedId, refresh]);

  const saveEdit = useCallback(async (id, field, value) => {
    const prompt = prompts.find(p => p.id === id);
    if (!prompt) return;
    await window.nockTerminal.prompts.save(id, { ...prompt, [field]: value });
    refresh();
  }, [prompts, refresh]);

  const selected = prompts.find(p => p.id === selectedId);

  if (selected) {
    return (
      <div className="flex flex-col h-full">
        <div className="px-3 py-2 border-b border-nock-border flex items-center justify-between shrink-0">
          <button onClick={() => { setSelectedId(null); setEditing(null); }}
            className="text-nock-text-muted hover:text-nock-text transition-colors text-[11px]">← Back</button>
          <div className="flex items-center gap-1">
            {onExecutePrompt && (
              <button onClick={() => onExecutePrompt(selected.body)} title="Execute"
                className="text-nock-green hover:text-green-300 transition-colors">
                <Play size={12} />
              </button>
            )}
            <button onClick={() => deletePrompt(selected.id)} title="Delete"
              className="text-nock-text-muted hover:text-nock-red transition-colors">
              <Trash2 size={12} />
            </button>
          </div>
        </div>
        <div className="px-3 py-2 border-b border-nock-border shrink-0">
          <input type="text" value={selected.title || ''} onChange={e => saveEdit(selected.id, 'title', e.target.value)}
            className="w-full bg-transparent text-nock-text text-[12px] font-medium focus:outline-none" placeholder="Prompt title" />
          <input type="text" value={(selected.tags || []).join(', ')} onChange={e => saveEdit(selected.id, 'tags', e.target.value.split(',').map(t => t.trim()).filter(Boolean))}
            className="w-full bg-transparent text-nock-text-muted text-[10px] font-mono focus:outline-none mt-1" placeholder="Tags (comma separated)" />
        </div>
        <div className="flex-1 overflow-auto p-2">
          <textarea value={selected.body || ''} onChange={e => saveEdit(selected.id, 'body', e.target.value)}
            className="w-full h-full bg-nock-card border border-nock-border rounded p-2 font-mono text-[11px] text-nock-text resize-none focus:outline-none focus:border-nock-accent-blue" />
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-2 border-b border-nock-border flex items-center justify-between shrink-0">
        <span className="font-mono text-[9px] text-nock-text-muted uppercase tracking-widest">// Prompts</span>
        <button onClick={createPrompt} className="text-nock-text-muted hover:text-nock-accent-purple transition-colors" title="New Prompt">
          <Plus size={12} />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto">
        {prompts.length === 0 && (
          <p className="font-mono text-[10px] text-nock-text-muted px-3 py-4 text-center">No saved prompts</p>
        )}
        {prompts.map(p => (
          <button key={p.id} onClick={() => setSelectedId(p.id)}
            className="w-full text-left px-3 py-2 hover:bg-nock-card transition-colors border-b border-nock-border/50">
            <span className="font-mono text-[10px] text-nock-text truncate block">{p.title || 'Untitled'}</span>
            {p.tags && p.tags.length > 0 && (
              <div className="flex items-center gap-1 mt-0.5">
                <Tag size={8} className="text-nock-text-muted" />
                <span className="font-mono text-[8px] text-nock-text-muted">{p.tags.join(', ')}</span>
              </div>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Wire prompt store into main.js and preload.js**

In `terminal-electron/electron/main.js`:
1. Add require: `const PromptStore = require('./prompt-store');`
2. Add variable: `let promptStore = null;`
3. In `initServices()`: `promptStore = new PromptStore();`
4. Add IPC handlers:
```javascript
  // Prompts
  ipcMain.handle('prompts:list', () => promptStore.list());
  ipcMain.handle('prompts:get', (_, id) => promptStore.get(id));
  ipcMain.handle('prompts:save', (_, { id, data }) => promptStore.save(id, data));
  ipcMain.handle('prompts:delete', (_, id) => promptStore.delete(id));
```

In `terminal-electron/electron/preload.js`:
```javascript
  // Prompts
  prompts: {
    list: () => ipcRenderer.invoke('prompts:list'),
    get: (id) => ipcRenderer.invoke('prompts:get', id),
    save: (id, data) => ipcRenderer.invoke('prompts:save', { id, data }),
    delete: (id) => ipcRenderer.invoke('prompts:delete', id),
  },
```

- [ ] **Step 4: Add prompt library panel to Sidebar.jsx**

Import and add to sidebar, similar to session history. In `terminal-electron/src/components/Sidebar.jsx`, add import:
```jsx
import PromptLibrary from './PromptLibrary';
```

Add a section after session history:
```jsx
          {/* Prompt Library */}
          <div className="border-t border-nock-border" style={{ maxHeight: '30%', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
            <PromptLibrary />
          </div>
```

- [ ] **Step 5: Verify prompt library**

```bash
cd terminal-electron
npm start
```

Check sidebar. Click "+" to create a new prompt. Edit title, tags, body. Verify it persists after restarting.

- [ ] **Step 6: Commit**

```bash
git add electron/prompt-store.js src/components/PromptLibrary.jsx electron/main.js electron/preload.js src/components/Sidebar.jsx
git commit -m "feat: add prompt library with Monaco editor"
```

---

## Task 9: UI Polish — Context Menus and Tab Management

**Files:**
- Create: `terminal-electron/src/components/ContextMenu.jsx`
- Modify: `terminal-electron/src/components/TabBar.jsx`
- Modify: `terminal-electron/src/components/Dashboard.jsx`
- Modify: `terminal-electron/src/components/FileTree.jsx`
- Modify: `terminal-electron/src/App.jsx`

- [ ] **Step 1: Create reusable ContextMenu.jsx**

Create `terminal-electron/src/components/ContextMenu.jsx`:

```jsx
import React, { useEffect, useRef } from 'react';

export default function ContextMenu({ x, y, items, onClose }) {
  const ref = useRef(null);

  useEffect(() => {
    const handler = (e) => {
      if (ref.current && !ref.current.contains(e.target)) onClose();
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [onClose]);

  // Clamp to viewport
  const menuW = 180;
  const menuH = items.length * 32 + 8;
  const clampedX = Math.max(0, Math.min(x, window.innerWidth - menuW - 4));
  const clampedY = Math.max(0, Math.min(y, window.innerHeight - menuH - 4));

  return (
    <div ref={ref}
      className="fixed bg-nock-card border border-nock-border rounded-lg shadow-2xl py-1 z-50 min-w-[170px] backdrop-blur-sm"
      style={{ left: clampedX, top: clampedY }}>
      {items.map((item, i) => {
        if (item.separator) {
          return <div key={i} className="border-t border-nock-border my-1" />;
        }
        return (
          <button key={i}
            onClick={() => { item.onClick(); onClose(); }}
            disabled={item.disabled}
            className={`w-full text-left px-3 py-1.5 text-[11px] transition-colors flex items-center gap-2 ${
              item.danger
                ? 'text-nock-red hover:bg-red-500/10'
                : 'text-nock-text hover:bg-nock-border-bright/30'
            } ${item.disabled ? 'opacity-40 pointer-events-none' : ''}`}>
            {item.icon && <span className="w-3.5 text-center">{item.icon}</span>}
            <span>{item.label}</span>
            {item.shortcut && <span className="ml-auto font-mono text-[9px] text-nock-text-muted">{item.shortcut}</span>}
          </button>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 2: Enhance TabBar with rename, pin, and expanded context menu**

Replace `terminal-electron/src/components/TabBar.jsx` with enhanced version that includes:
- Double-click to rename (inline input)
- Pin indicator (dot)
- Expanded context menu using ContextMenu component
- Drag-and-drop reorder

```jsx
import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Pin } from 'lucide-react';
import ContextMenu from './ContextMenu';

const STATUS_COLORS = {
  active:   'bg-nock-green',
  recent:   'bg-nock-yellow',
  inactive: 'bg-nock-text-muted',
};

export default function TabBar({ tabs, activeTabId, onTabClick, onTabClose, onNewTab, getSessionStatus, onTabRename, onTabPin, onTabDuplicate, onSplit, onTabReorder }) {
  const [contextMenu, setContextMenu] = useState(null);
  const [editingTabId, setEditingTabId] = useState(null);
  const [editValue, setEditValue] = useState('');
  const [dragTabId, setDragTabId] = useState(null);
  const editInputRef = useRef(null);

  useEffect(() => {
    if (editingTabId && editInputRef.current) {
      editInputRef.current.focus();
      editInputRef.current.select();
    }
  }, [editingTabId]);

  const handleContextMenu = (e, tab) => {
    e.preventDefault();
    setContextMenu({ x: e.clientX, y: e.clientY, tab });
  };

  const startRename = useCallback((tab) => {
    setEditingTabId(tab.id);
    setEditValue(tab.title);
  }, []);

  const commitRename = useCallback(() => {
    if (editingTabId && editValue.trim()) {
      onTabRename?.(editingTabId, editValue.trim());
    }
    setEditingTabId(null);
  }, [editingTabId, editValue, onTabRename]);

  const handleDragStart = (e, tabId) => {
    setDragTabId(tabId);
    e.dataTransfer.effectAllowed = 'move';
  };

  const handleDragOver = (e, targetTabId) => {
    e.preventDefault();
    if (dragTabId && dragTabId !== targetTabId) {
      onTabReorder?.(dragTabId, targetTabId);
      setDragTabId(targetTabId); // Update reference since order changed
    }
  };

  const handleDragEnd = () => setDragTabId(null);

  const contextItems = contextMenu ? [
    { label: 'Rename', onClick: () => startRename(contextMenu.tab) },
    { label: contextMenu.tab.pinned ? 'Unpin' : 'Pin', onClick: () => onTabPin?.(contextMenu.tab.id) },
    { separator: true },
    { label: 'Split Terminal', onClick: () => onSplit?.() },
    { label: 'Duplicate', onClick: () => onTabDuplicate?.(contextMenu.tab) },
    { separator: true },
    { label: 'Close', onClick: () => onTabClose(contextMenu.tab.id), disabled: contextMenu.tab.pinned },
    { label: 'Close Others', onClick: () => tabs.forEach(t => { if (t.id !== contextMenu.tab.id && !t.pinned) onTabClose(t.id); }), danger: true },
  ] : [];

  return (
    <div className="bg-nock-bg flex items-center shrink-0 h-9 relative flex-1">
      <div className="flex-1 flex items-center overflow-x-auto no-scrollbar">
        {tabs.map((tab) => {
          const isActive = tab.id === activeTabId;
          const isEditing = editingTabId === tab.id;
          return (
            <div
              key={tab.id}
              draggable={!isEditing}
              onDragStart={(e) => handleDragStart(e, tab.id)}
              onDragOver={(e) => handleDragOver(e, tab.id)}
              onDragEnd={handleDragEnd}
              onClick={() => onTabClick(tab.id)}
              onContextMenu={(e) => handleContextMenu(e, tab)}
              onDoubleClick={() => startRename(tab)}
              className={`group relative flex items-center gap-2 px-3.5 h-9 cursor-pointer shrink-0 max-w-[220px] transition-all ${
                isActive ? 'bg-nock-card text-nock-text' : 'text-nock-text-dim hover:text-nock-text hover:bg-nock-card/40'
              } ${dragTabId === tab.id ? 'opacity-50' : ''}`}
            >
              {isActive && (
                <div className="absolute bottom-0 left-0 right-0 h-[2px] bg-gradient-to-r from-nock-accent-blue via-nock-accent-purple to-nock-accent-cyan" />
              )}
              <div className="absolute right-0 top-2 bottom-2 w-px bg-nock-border" />

              {tab.pinned && <Pin size={9} className="text-nock-accent-purple shrink-0" />}

              <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                (() => {
                  const status = getSessionStatus?.(tab.id) || tab.status;
                  if (status === 'ready') return 'bg-nock-green';
                  if (status === 'active') return 'bg-nock-yellow animate-pulse-glow';
                  return 'bg-red-400';
                })()
              }`} />

              {isEditing ? (
                <input ref={editInputRef} value={editValue} onChange={e => setEditValue(e.target.value)}
                  onBlur={commitRename} onKeyDown={e => { if (e.key === 'Enter') commitRename(); if (e.key === 'Escape') setEditingTabId(null); }}
                  className="bg-transparent text-[11px] text-nock-text focus:outline-none w-20 border-b border-nock-accent-blue"
                  onClick={e => e.stopPropagation()} />
              ) : (
                <span className="text-[11px] truncate font-medium">{tab.title}</span>
              )}

              {tab.branch && !isEditing && (
                <span className="font-mono text-[9px] text-nock-accent-blue truncate hidden sm:inline tracking-tight">{tab.branch}</span>
              )}

              {!tab.pinned && (
                <button
                  onClick={(e) => { e.stopPropagation(); onTabClose(tab.id); }}
                  className={`ml-auto shrink-0 w-4 h-4 flex items-center justify-center rounded hover:bg-white/10 transition-all ${
                    isActive ? 'opacity-60 hover:opacity-100' : 'opacity-0 group-hover:opacity-60 hover:!opacity-100'
                  }`}>
                  <svg className="w-2.5 h-2.5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 12 12">
                    <path d="M2 2l8 8M10 2l-8 8" />
                  </svg>
                </button>
              )}
            </div>
          );
        })}
      </div>

      <button onClick={() => onNewTab()} className="w-9 h-9 flex items-center justify-center text-nock-text-muted hover:text-nock-accent-purple hover:bg-nock-card/40 transition-colors shrink-0 border-l border-nock-border" title="New Tab (Ctrl+T)">
        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
        </svg>
      </button>

      {contextMenu && (
        <ContextMenu x={contextMenu.x} y={contextMenu.y} items={contextItems} onClose={() => setContextMenu(null)} />
      )}
    </div>
  );
}
```

- [ ] **Step 3: Add tab management callbacks in App.jsx**

In `terminal-electron/src/App.jsx`, add these callbacks (after the existing `closeSplit` definition):

```jsx
  const renameTab = useCallback((tabId, title) => {
    setTabs(prev => prev.map(t => t.id === tabId ? { ...t, title } : t));
  }, []);

  const pinTab = useCallback((tabId) => {
    setTabs(prev => prev.map(t => t.id === tabId ? { ...t, pinned: !t.pinned } : t));
  }, []);

  const duplicateTab = useCallback((tab) => {
    const tabId = `tab-${Date.now()}`;
    const newTab = { ...tab, id: tabId, pinned: false };
    setTabs(prev => [...prev, newTab]);
    setActiveTabId(tabId);
  }, []);

  const reorderTabs = useCallback((dragId, targetId) => {
    setTabs(prev => {
      const arr = [...prev];
      const dragIdx = arr.findIndex(t => t.id === dragId);
      const targetIdx = arr.findIndex(t => t.id === targetId);
      if (dragIdx === -1 || targetIdx === -1) return prev;
      const [dragged] = arr.splice(dragIdx, 1);
      arr.splice(targetIdx, 0, dragged);
      return arr;
    });
  }, []);
```

Update the TabBar usage to pass these new props:
```jsx
              <TabBar
                tabs={tabs}
                activeTabId={activeTabId}
                onTabClick={(id) => setActiveTabId(id)}
                onTabClose={closeTab}
                onNewTab={openNewTab}
                getSessionStatus={getSessionStatus}
                onTabRename={renameTab}
                onTabPin={pinTab}
                onTabDuplicate={duplicateTab}
                onSplit={toggleTerminalSplit}
                onTabReorder={reorderTabs}
              />
```

- [ ] **Step 4: Add context menus to Dashboard project cards and FileTree**

For `Dashboard.jsx`: read the current file, add right-click handler to project cards with items: Open Terminal, Open in VS Code (`code .`), Open in Explorer, Project Settings, Copy Path.

For `FileTree.jsx`: read the current file, add right-click handler to file/folder items with items: Open in Editor, Open in Explorer, Copy Path, Copy Content.

Both should use the `ContextMenu` component and `ProjectSettingsModal` for project settings.

(These modifications follow the same pattern as TabBar — add `onContextMenu` handler, render `<ContextMenu>` with appropriate items, import from `./ContextMenu`.)

- [ ] **Step 5: Verify all UI polish features**

```bash
cd terminal-electron
npm start
```

Test:
- Right-click a tab → context menu with Rename, Pin, Split, Duplicate, Close, Close Others
- Double-click a tab → inline rename
- Drag tabs to reorder
- Pinned tabs show pin icon, can't be closed with X button

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: add tab management (reorder, rename, pin) and context menus"
```

---

## Task 10: Final Verification and Cleanup

- [ ] **Step 1: Full app test**

```bash
cd terminal-electron
npm start
```

Test every feature:
1. Settings: all sections render, changes persist after reload
2. Status bar: shows on all views, Ollama status, clock
3. Model selector: dynamic models from Ollama, Kit opens terminal, Mara opens browser
4. Telegram: test notification sends successfully
5. Project profiles: save and load per-project settings
6. Session history: sessions logged, output captured (if enabled)
7. Prompt library: create, edit, delete prompts
8. Tab management: rename, pin, reorder, context menu
9. Keyboard shortcuts still work

- [ ] **Step 2: Build production bundle**

```bash
cd terminal-electron
npm run build
```

Verify no build errors.

- [ ] **Step 3: Commit any remaining fixes**

```bash
git add -A
git status
# Only commit if there are changes
git commit -m "fix: address Phase 3 integration issues"
```
