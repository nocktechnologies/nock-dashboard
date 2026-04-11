const {
  app,
  BrowserWindow,
  Menu,
  Tray,
  Notification,
  globalShortcut,
  ipcMain,
  nativeImage,
  screen,
  shell,
} = require('electron');
const path = require('path');
const Store = require('electron-store');

const NOCKCC_URL = 'https://cc.nocktechnologies.io';
const store = new Store();
const DEFAULT_BOUNDS = { width: 1400, height: 900, x: undefined, y: undefined };

let mainWindow;
let tray;

// ---------------------------------------------------------------------------
// Window state persistence
// ---------------------------------------------------------------------------

function getWindowState() {
  const bounds = store.get('windowBounds', DEFAULT_BOUNDS);
  if (bounds.x === undefined || bounds.y === undefined) return bounds;

  // Verify saved position is visible on a connected display
  const isVisible = screen.getAllDisplays().some((display) => {
    const { x, y, width, height } = display.workArea;
    return bounds.x >= x - bounds.width + 100
      && bounds.x < x + width - 100
      && bounds.y >= y
      && bounds.y < y + height - 100;
  });

  return isVisible ? bounds : DEFAULT_BOUNDS;
}

function saveWindowState() {
  if (mainWindow && !mainWindow.isDestroyed()) {
    store.set('windowBounds', mainWindow.getBounds());
  }
}

// ---------------------------------------------------------------------------
// Window creation
// ---------------------------------------------------------------------------

function createWindow() {
  const bounds = getWindowState();

  mainWindow = new BrowserWindow({
    ...bounds,
    minWidth: 800,
    minHeight: 600,
    titleBarStyle: 'hiddenInset',
    trafficLightPosition: { x: 16, y: 12 },
    backgroundColor: '#000000',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
    },
    icon: path.join(__dirname, 'assets', 'icon.icns'),
    show: false,
  });

  // Make web content clickable under the title bar drag region
  mainWindow.webContents.on('did-finish-load', () => {
    mainWindow.webContents.insertCSS(`
      body { -webkit-app-region: no-drag; padding-top: 2px; }
    `);
  });

  // Show loading screen first
  mainWindow.loadFile(path.join(__dirname, 'renderer', 'index.html'));

  // Once loading screen renders, navigate to production
  mainWindow.webContents.once('did-finish-load', () => {
    mainWindow.show();
    mainWindow.loadURL(NOCKCC_URL);
  });

  // Handle load failures (offline / server down)
  mainWindow.webContents.on('did-fail-load', (_event, errorCode, _desc, validatedURL) => {
    // Ignore sub-resource failures and aborted loads (-3)
    if (errorCode === -3) return;
    if (validatedURL && validatedURL.startsWith(NOCKCC_URL)) {
      mainWindow.loadFile(path.join(__dirname, 'renderer', 'offline.html'));
    }
  });

  // Open external links in the default browser (protocol-restricted)
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (!url.startsWith(NOCKCC_URL)) {
      let parsed;
      try { parsed = new URL(url); } catch { return { action: 'deny' }; }
      if (parsed.protocol === 'https:' || parsed.protocol === 'http:') {
        shell.openExternal(url);
      }
      return { action: 'deny' };
    }
    return { action: 'allow' };
  });

  // Persist window state on move/resize
  mainWindow.on('resize', saveWindowState);
  mainWindow.on('move', saveWindowState);
  mainWindow.on('close', saveWindowState);
}

// ---------------------------------------------------------------------------
// Navigation helper
// ---------------------------------------------------------------------------

function navigateTo(urlPath) {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.loadURL(NOCKCC_URL + urlPath);
    mainWindow.show();
    mainWindow.focus();
  }
}

// ---------------------------------------------------------------------------
// Native menu bar
// ---------------------------------------------------------------------------

function buildMenu() {
  const template = [
    {
      label: 'NockCC',
      submenu: [
        { label: 'About NockCC', role: 'about' },
        { type: 'separator' },
        {
          label: 'Preferences...',
          accelerator: 'Cmd+,',
          click: () => navigateTo('/settings/'),
        },
        { type: 'separator' },
        { role: 'hide' },
        { role: 'hideOthers' },
        { role: 'unhide' },
        { type: 'separator' },
        { role: 'quit' },
      ],
    },
    {
      label: 'Navigate',
      submenu: [
        { label: 'Nerve Center', accelerator: 'Cmd+1', click: () => navigateTo('/') },
        { label: 'Pipeline', accelerator: 'Cmd+2', click: () => navigateTo('/pipeline/') },
        { label: 'Sessions', accelerator: 'Cmd+3', click: () => navigateTo('/sessions/') },
        { label: 'Brain', accelerator: 'Cmd+4', click: () => navigateTo('/brain/') },
        { label: 'Tasks', accelerator: 'Cmd+5', click: () => navigateTo('/tasks/') },
        { label: 'Spend', accelerator: 'Cmd+6', click: () => navigateTo('/spend/') },
        { label: 'Teams', accelerator: 'Cmd+7', click: () => navigateTo('/teams/') },
        { type: 'separator' },
        {
          label: 'Chat',
          accelerator: 'Cmd+Shift+C',
          click: () => navigateTo('/remote/chat/'),
        },
        {
          label: 'AI Advisor',
          accelerator: 'Cmd+Shift+A',
          click: () => navigateTo('/intelligence/advisor/'),
        },
        {
          label: 'Executive Dashboard',
          accelerator: 'Cmd+Shift+E',
          click: () => navigateTo('/intelligence/executive/'),
        },
      ],
    },
    {
      label: 'View',
      submenu: [
        { role: 'reload' },
        { role: 'forceReload' },
        { type: 'separator' },
        { role: 'zoomIn' },
        { role: 'zoomOut' },
        { role: 'resetZoom' },
        { type: 'separator' },
        { role: 'togglefullscreen' },
      ],
    },
    {
      label: 'Edit',
      submenu: [
        { role: 'undo' },
        { role: 'redo' },
        { type: 'separator' },
        { role: 'cut' },
        { role: 'copy' },
        { role: 'paste' },
        { role: 'selectAll' },
      ],
    },
    {
      label: 'Window',
      submenu: [
        { role: 'minimize' },
        { role: 'zoom' },
        { type: 'separator' },
        { role: 'front' },
      ],
    },
  ];

  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

// ---------------------------------------------------------------------------
// Tray icon
// ---------------------------------------------------------------------------

function createTray() {
  const trayIconPath = path.join(__dirname, 'assets', 'tray-icon.png');
  const trayImage = nativeImage.createFromPath(trayIconPath).resize({ width: 22, height: 22 });
  trayImage.setTemplateImage(true);

  tray = new Tray(trayImage);
  tray.setToolTip('NockCC — Command Center');

  const trayMenu = Menu.buildFromTemplate([
    { label: 'Open NockCC', click: () => { mainWindow.show(); mainWindow.focus(); } },
    { type: 'separator' },
    { label: 'Nerve Center', click: () => navigateTo('/') },
    { label: 'Pipeline', click: () => navigateTo('/pipeline/') },
    { label: 'Sessions', click: () => navigateTo('/sessions/') },
    { label: 'Brain', click: () => navigateTo('/brain/') },
    { label: 'Tasks', click: () => navigateTo('/tasks/') },
    { label: 'Teams', click: () => navigateTo('/teams/') },
    { type: 'separator' },
    { label: 'Quit NockCC', role: 'quit' },
  ]);

  tray.setContextMenu(trayMenu);
  tray.on('click', () => {
    mainWindow.show();
    mainWindow.focus();
  });
}

// ---------------------------------------------------------------------------
// Native notifications (from web page via preload bridge)
// ---------------------------------------------------------------------------

ipcMain.on('show-notification', (_event, { title, body, url }) => {
  const notification = new Notification({
    title,
    body,
    icon: path.join(__dirname, 'assets', 'icon.png'),
    silent: false,
  });

  notification.on('click', () => {
    mainWindow.show();
    mainWindow.focus();
    if (url) navigateTo(url);
  });

  notification.show();
});

// ---------------------------------------------------------------------------
// IPC: retry connection from offline page
// ---------------------------------------------------------------------------

ipcMain.on('retry-connection', () => {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.loadURL(NOCKCC_URL);
  }
});

// ---------------------------------------------------------------------------
// App lifecycle
// ---------------------------------------------------------------------------

app.whenReady().then(() => {
  buildMenu();
  createWindow();
  createTray();

  // Global shortcut: Cmd+Shift+N to toggle NockCC window
  globalShortcut.register('CommandOrControl+Shift+N', () => {
    if (mainWindow.isVisible() && mainWindow.isFocused()) {
      mainWindow.hide();
    } else {
      mainWindow.show();
      mainWindow.focus();
    }
  });

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    } else {
      mainWindow.show();
      mainWindow.focus();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('will-quit', () => {
  globalShortcut.unregisterAll();
});
