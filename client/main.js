const { app, BrowserWindow, nativeTheme, ipcMain, Menu, shell } = require('electron');
const fs = require('fs');
const path = require('path');
const pty = require('node-pty');

const DEFAULT_TERMINAL_COLS = 120;
const DEFAULT_TERMINAL_ROWS = 30;

function resolveTerminalCwd(cwd) {
  const raw = typeof cwd === 'string' ? cwd.trim() : '';
  if (!raw) {
    throw new Error('缺少项目目录');
  }

  const resolved = path.resolve(raw);
  const stat = fs.statSync(resolved);
  if (!stat.isDirectory()) {
    throw new Error('项目目录不存在或不是文件夹');
  }
  return resolved;
}

function normalizeTerminalPayload(payload) {
  if (payload && typeof payload === 'object') return payload;
  return { cwd: payload };
}

function clampTerminalSize(value, fallback) {
  const num = Number(value);
  if (!Number.isFinite(num)) return fallback;
  return Math.max(2, Math.min(500, Math.floor(num)));
}

function setApplicationMenu(mainWindow) {
  const sendCommand = (command) => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('app-menu-command', command);
    }
  };

  const template = [
    {
      label: '文件',
      submenu: [
        { label: '新建对话', accelerator: 'CmdOrCtrl+N', click: () => sendCommand('new-chat') },
        { label: '打开当前项目到 VS Code', accelerator: 'CmdOrCtrl+Shift+O', click: () => sendCommand('open-current-vscode') },
        { type: 'separator' },
        { label: process.platform === 'darwin' ? '关闭窗口' : '退出', role: process.platform === 'darwin' ? 'close' : 'quit' },
      ],
    },
    {
      label: '编辑',
      submenu: [
        { label: '撤销', role: 'undo' },
        { label: '重做', role: 'redo' },
        { type: 'separator' },
        { label: '剪切', role: 'cut' },
        { label: '复制', role: 'copy' },
        { label: '粘贴', role: 'paste' },
        { label: '全选', role: 'selectAll' },
      ],
    },
    {
      label: '查看',
      submenu: [
        { label: '切换侧边栏', accelerator: 'CmdOrCtrl+B', click: () => sendCommand('toggle-sidebar') },
        { type: 'separator' },
        { label: '重新加载', role: 'reload' },
        { label: '强制重新加载', role: 'forceReload' },
        { label: '开发者工具', role: 'toggleDevTools' },
        { type: 'separator' },
        { label: '实际大小', role: 'resetZoom' },
        { label: '放大', role: 'zoomIn' },
        { label: '缩小', role: 'zoomOut' },
        { type: 'separator' },
        { label: '全屏', role: 'togglefullscreen' },
      ],
    },
    {
      label: '窗口',
      submenu: [
        { label: '最小化', role: 'minimize' },
        { label: '缩放', role: 'zoom' },
        { type: 'separator' },
        { label: '关闭窗口', role: 'close' },
      ],
    },
    {
      label: '帮助',
      submenu: [
        { label: '打开应用目录', click: () => shell.openPath(__dirname) },
        { label: 'Electron 文档', click: () => shell.openExternal('https://www.electronjs.org/docs/latest') },
      ],
    },
  ];

  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

function createWindow() {
  // 强制深色模式，让原生菜单栏/标题栏跟随深色主题
  nativeTheme.themeSource = 'dark';

  const win = new BrowserWindow({
    width: 1560,
    height: 1070,
    // 背景色与聊天界面一致，避免加载瞬间白屏
    backgroundColor: '#0d0d0d',
    titleBarStyle: 'default',
    autoHideMenuBar: false,
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

  const terminalSessions = new Map();
  const sendTerminalEvent = (payload) => {
    for (const target of BrowserWindow.getAllWindows()) {
      if (!target.isDestroyed()) {
        target.webContents.send('terminal-event', payload);
      }
    }
  };
  const terminalSnapshot = (session) => ({
    sessionId: session.id,
    cwd: session.cwd,
    title: session.title,
    status: session.status,
    buffer: session.buffer,
    cols: session.cols,
    rows: session.rows,
  });
  const appendTerminalBuffer = (session, data) => {
    const text = String(data || '');
    if (!text) return;
    session.buffer = (session.buffer + text).slice(-120000);
  };
  const stopTerminal = (sessionId) => {
    const session = terminalSessions.get(String(sessionId || ''));
    if (!session) return { ok: true };
    session.closedByUser = true;
    terminalSessions.delete(session.id);
    sendTerminalEvent({ type: 'closed', sessionId: session.id });
    try {
      session.pty.kill();
    } catch (e) {
      void e;
    }
    return { ok: true };
  };
  const createTerminalWindow = (sessionId) => {
    const childWin = new BrowserWindow({
      width: 980,
      height: 620,
      minWidth: 560,
      minHeight: 360,
      backgroundColor: '#101418',
      titleBarStyle: 'default',
      autoHideMenuBar: false,
      webPreferences: {
        preload: path.join(__dirname, 'preload.js'),
        contextIsolation: true,
      },
    });

    const devUrl = process.env.VITE_DEV_SERVER_URL || 'http://localhost:5173';
    const query = `terminalWindow=1&sessionId=${encodeURIComponent(sessionId)}`;
    if (
      process.env.NODE_ENV === 'development' ||
      process.env.VITE_DEV_SERVER_URL ||
      process.env.npm_lifecycle_event === 'dev'
    ) {
      childWin.loadURL(`${devUrl}?${query}`);
    } else {
      childWin.loadFile(path.join(__dirname, 'dist', 'index.html'), { query: { terminalWindow: '1', sessionId } });
    }
  };

  ipcMain.handle('terminal-open-powershell', async (_event, payload) => {
    const request = normalizeTerminalPayload(payload);
    const resolved = resolveTerminalCwd(request.cwd);
    const cols = clampTerminalSize(request.cols, DEFAULT_TERMINAL_COLS);
    const rows = clampTerminalSize(request.rows, DEFAULT_TERMINAL_ROWS);
    const command = process.platform === 'win32' ? 'powershell.exe' : (process.env.SHELL || 'pwsh');
    const args = process.platform === 'win32' ? ['-NoLogo'] : [];
    const sessionId = `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;

    const ptyProcess = pty.spawn(command, args, {
      name: 'xterm-256color',
      cols,
      rows,
      cwd: resolved,
      env: {
        ...process.env,
        TERM: 'xterm-256color',
        COLORTERM: 'truecolor',
        FORCE_COLOR: '1',
      },
    });

    const session = {
      id: sessionId,
      cwd: resolved,
      pty: ptyProcess,
      title: path.basename(resolved) || resolved,
      status: 'running',
      buffer: '',
      cols,
      rows,
    };
    terminalSessions.set(sessionId, session);
    sendTerminalEvent({ type: 'started', sessionId, cwd: resolved, title: session.title, cols, rows });

    ptyProcess.onData((data) => {
      appendTerminalBuffer(session, data);
      sendTerminalEvent({ type: 'output', sessionId, data });
    });
    ptyProcess.onExit(({ exitCode, signal }) => {
      if (session.closedByUser) return;
      session.status = 'exited';
      sendTerminalEvent({ type: 'exit', sessionId, code: exitCode, signal });
    });

    return { ok: true, cwd: resolved, sessionId, reused: false, title: session.title, cols, rows };
  });
  ipcMain.handle('terminal-list', () => ({
    ok: true,
    sessions: [...terminalSessions.values()].map(terminalSnapshot),
  }));
  ipcMain.handle('terminal-write', (_event, payload) => {
    const sessionId = typeof payload === 'object' && payload ? payload.sessionId : '';
    const input = typeof payload === 'object' && payload ? payload.input : payload;
    const session = terminalSessions.get(String(sessionId || ''));
    if (!session || session.status === 'exited') {
      throw new Error('终端未启动');
    }
    session.pty.write(String(input || ''));
    return { ok: true };
  });
  ipcMain.handle('terminal-resize', (_event, payload) => {
    const sessionId = typeof payload === 'object' && payload ? payload.sessionId : '';
    const session = terminalSessions.get(String(sessionId || ''));
    if (!session || session.status === 'exited') return { ok: true };
    const cols = clampTerminalSize(payload?.cols, session.cols || DEFAULT_TERMINAL_COLS);
    const rows = clampTerminalSize(payload?.rows, session.rows || DEFAULT_TERMINAL_ROWS);
    try {
      session.pty.resize(cols, rows);
      session.cols = cols;
      session.rows = rows;
    } catch (e) {
      void e;
    }
    return { ok: true };
  });
  ipcMain.handle('terminal-close', (_event, sessionId) => stopTerminal(sessionId));
  ipcMain.handle('open-in-vscode', async (_event, targetPath) => {
    const { exec } = require('child_process');
    const resolved = path.resolve(String(targetPath || ''));
    return new Promise((resolve) => {
      exec(`code "${resolved}"`, (err) => {
        if (err) resolve({ ok: false, error: err.message });
        else resolve({ ok: true });
      });
    });
  });

  ipcMain.handle('terminal-popout', (_event, sessionId) => {
    const sid = String(sessionId || '');
    if (!terminalSessions.has(sid)) {
      throw new Error('终端未启动');
    }
    createTerminalWindow(sid);
    return { ok: true };
  });
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

  setApplicationMenu(win);
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
