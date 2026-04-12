const { app, BrowserWindow, nativeTheme, ipcMain } = require('electron');
const path = require('path');

function createWindow() {
  // 强制深色模式，让原生菜单栏/标题栏跟随深色主题
  nativeTheme.themeSource = 'dark';

  const win = new BrowserWindow({
    width: 1560,
    height: 1070,
    // 背景色与聊天界面一致，避免加载瞬间白屏
    backgroundColor: '#0d0d0d',
    // Windows 11 深色标题栏，隐藏默认边框/白边
    titleBarStyle: 'hidden',
    titleBarOverlay: {
      color: '#0d0d0d',
      symbolColor: '#888888',
      height: 32,
    },
    // 自动隐藏菜单栏，按 Alt 键可临时显示
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
    },
  });

  // 通知渲染进程当前最大化状态（用于显示/隐藏还原按钮）
  win.on('maximize', () => { win.webContents.send('window-state-changed', true) });
  win.on('unmaximize', () => { win.webContents.send('window-state-changed', false) });

  // IPC 窗口控制
  ipcMain.handle('window-minimize', () => win.minimize());
  ipcMain.handle('window-maximize-toggle', () => {
    if (win.isMaximized()) win.unmaximize(); else win.maximize();
  });
  ipcMain.handle('window-close', () => win.close());
  ipcMain.handle('window-is-maximized', () => win.isMaximized());

  const devUrl = process.env.VITE_DEV_SERVER_URL || 'http://localhost:5173';
  if (
    process.env.NODE_ENV === 'development' ||
    process.env.VITE_DEV_SERVER_URL ||
    process.env.npm_lifecycle_event === 'dev'
  ) {
    win.loadURL(devUrl);
    win.webContents.openDevTools();
  } else {
    win.loadFile(path.join(__dirname, 'dist', 'index.html'));
  }
}

app.whenReady().then(() => {
  createWindow();
  app.on('activate', function () {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', function () {
  if (process.platform !== 'darwin') app.quit();
});
