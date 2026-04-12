const { contextBridge } = require('electron');

// Expose a safe environment variable to renderer
contextBridge.exposeInMainWorld('env', {
  BACKEND_URL: process.env.BACKEND_URL || 'http://127.0.0.1:8000',
});
