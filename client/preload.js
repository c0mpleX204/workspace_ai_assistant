const { contextBridge, ipcRenderer } = require('electron');

// Expose a safe environment variable to renderer
contextBridge.exposeInMainWorld('env', {
  BACKEND_URL: process.env.BACKEND_URL || 'http://127.0.0.1:8000',
});

contextBridge.exposeInMainWorld('windowApi', {
  minimize: () => ipcRenderer.invoke('window-minimize'),
  maximizeToggle: () => ipcRenderer.invoke('window-maximize-toggle'),
  close: () => ipcRenderer.invoke('window-close'),
  isMaximized: () => ipcRenderer.invoke('window-is-maximized'),
  openPowerShell: (cwd, options = {}) => ipcRenderer.invoke('terminal-open-powershell', { cwd, ...options }),
  listTerminals: () => ipcRenderer.invoke('terminal-list'),
  writeTerminal: (sessionId, input) => ipcRenderer.invoke('terminal-write', { sessionId, input }),
  resizeTerminal: (sessionId, cols, rows) => ipcRenderer.invoke('terminal-resize', { sessionId, cols, rows }),
  closeTerminal: (sessionId) => ipcRenderer.invoke('terminal-close', sessionId),
  popoutTerminal: (sessionId) => ipcRenderer.invoke('terminal-popout', sessionId),
  onStateChanged: (callback) => {
    const handler = (_event, isMaximized) => callback(Boolean(isMaximized));
    ipcRenderer.on('window-state-changed', handler);
    return () => ipcRenderer.removeListener('window-state-changed', handler);
  },
  openInVSCode: (targetPath) => ipcRenderer.invoke('open-in-vscode', targetPath),
  onAppMenuCommand: (callback) => {
    const handler = (_event, command) => callback(String(command || ''));
    ipcRenderer.on('app-menu-command', handler);
    return () => ipcRenderer.removeListener('app-menu-command', handler);
  },
  onTerminalEvent: (callback) => {
    const handler = (_event, payload) => callback(payload || {});
    ipcRenderer.on('terminal-event', handler);
    return () => ipcRenderer.removeListener('terminal-event', handler);
  },
});
