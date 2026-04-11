# NockCC Desktop

Native macOS app for the NockCC Command Center. Electron wrapper around [cc.nocktechnologies.io](https://cc.nocktechnologies.io) with dock icon, native notifications, keyboard shortcuts, and menu bar presence.

## Quick Start

```bash
cd desktop
npm install
npm start
```

The app loads the production NockCC dashboard from Railway. If the server is unreachable, an offline screen with a retry button is shown.

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| Cmd+1 | Nerve Center |
| Cmd+2 | Pipeline |
| Cmd+3 | Sessions |
| Cmd+4 | Brain |
| Cmd+5 | Tasks |
| Cmd+6 | Spend |
| Cmd+7 | Teams |
| Cmd+Shift+C | Chat |
| Cmd+Shift+A | AI Advisor |
| Cmd+Shift+E | Executive Dashboard |
| Cmd+Shift+N | Toggle NockCC window (global) |
| Cmd+, | Preferences |

## Features

- **Hidden inset title bar** — native Mac traffic lights, pitch-black background
- **Navigate menu** — quick access to all NockCC sections via keyboard shortcuts
- **Menu bar tray icon** — always-accessible quick navigation
- **Global shortcut** — Cmd+Shift+N toggles the window from anywhere
- **Native notifications** — macOS notification center integration via IPC bridge
- **Window state persistence** — remembers position and size between launches
- **Session persistence** — cookies persist so you stay logged in
- **Offline handling** — shows retry screen when server is unreachable
- **External links** — open in default browser, not inside the app

## Build for Distribution

```bash
# Full build (icons + .dmg + .zip)
chmod +x scripts/build-mac.sh
./scripts/build-mac.sh

# Or step by step
npm install
npm run icons    # Generate .icns and tray icon from SVG
npm run build    # Build .app, .dmg, .zip in dist/
```

Output goes to `dist/`. The DMG can be distributed directly.

## App Icon

Run `npm run icons` to regenerate the app icon. This uses macOS built-in `qlmanage`, `sips`, and `iconutil` to produce:

- `assets/icon.png` — 1024x1024 source
- `assets/icon.icns` — macOS app bundle icon
- `assets/tray-icon.png` — 22x22 menu bar icon

## Architecture

```
desktop/
├── main.js              # Electron main process (window, menu, tray, shortcuts)
├── preload.js           # IPC bridge (notifications, retry)
├── renderer/
│   ├── index.html       # Loading screen (shown while NockCC loads)
│   └── offline.html     # Offline screen (server unreachable)
├── assets/
│   ├── icon.png         # 1024x1024 app icon
│   ├── icon.icns        # macOS .icns bundle
│   └── tray-icon.png    # 22x22 menu bar icon
├── scripts/
│   ├── build-mac.sh     # Full build script
│   └── generate-icons.js # Icon generation from SVG
├── electron-builder.yml # Build configuration
└── package.json
```

The app is a thin wrapper — all business logic lives in the Django backend on Railway. The Electron shell adds native Mac integration on top.
