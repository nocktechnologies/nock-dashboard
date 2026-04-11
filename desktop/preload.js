const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('nockcc', {
  platform: process.platform,
  version: require('./package.json').version,

  // Retry connection from offline page
  retry: () => ipcRenderer.send('retry-connection'),

  // Trigger native Mac notification from the web page
  showNotification: (payload) => ipcRenderer.send('show-notification', payload),
});
