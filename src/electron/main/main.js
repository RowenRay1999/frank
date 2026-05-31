const { app, BrowserWindow, Tray, Menu, nativeImage, screen } = require('electron');
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');
const WebSocket = require('ws');
const { loadConfig } = require('./config');
const { createIPC } = require('./ipc');

// ─── 全局状态 ───────────────────────────────────────────
let mainWindow = null;
let tray = null;
let pythonProcess = null;
let wsConnection = null;
let wsReconnectTimer = null;
let wsReconnectAttempt = 0;
let config = null;
let currentState = { name: 'Idle', timeInState: 0 };
let currentIdentity = null;  // Phase 2
let trayUpdateInterval = null;  // WR-03: track for cleanup
let previewWindow = null;  // 预览窗口

// ─── 开机自启 ────────────────────────────────────────────
function setAutoStart(enabled) {
  // Windows: HKCU\Software\Microsoft\Windows\CurrentVersion\Run
  try {
    const { spawnSync } = require('child_process');
    const appPath = process.execPath;
    const regKey = 'HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run';
    const regValue = 'Frank';

    if (enabled) {
      spawnSync('reg', ['add', regKey, '/v', regValue, '/t', 'REG_SZ', '/d', appPath, '/f']);
      console.log('[Frank] Auto-start enabled');
    } else {
      spawnSync('reg', ['delete', regKey, '/v', regValue, '/f']);
      console.log('[Frank] Auto-start disabled');
    }
  } catch (err) {
    console.warn('[Frank] Failed to configure auto-start:', err.message);
  }
}

// ─── Python 子进程管理 ──────────────────────────────────
function spawnPython() {
  const pythonExe = path.join(__dirname, '..', '..', '..', '.venv', 'Scripts', 'python.exe');
  const serverEntry = path.join(__dirname, '..', '..', 'python', 'server', 'main.py');
  const projectRoot = path.join(__dirname, '..', '..', '..');

  console.log('[Frank] Starting Python inference service...');
  pythonProcess = spawn(pythonExe, [serverEntry], {
    cwd: projectRoot,
    stdio: ['pipe', 'pipe', 'pipe'],
  });

  pythonProcess.stdout.on('data', (data) => {
    const text = data.toString().trim();
    console.log(`[Python] ${text}`);
    // 检测 Python 服务就绪信号，立即连接 WebSocket
    if (text.includes('Frank Inference Service ready')) {
      console.log('[Frank] Python service ready, connecting WebSocket...');
      connectWebSocket();
    }
  });

  pythonProcess.stderr.on('data', (data) => {
    console.error(`[Python:err] ${data.toString().trim()}`);
  });

  pythonProcess.on('close', (code) => {
    console.log(`[Frank] Python process exited with code ${code}`);
    pythonProcess = null;
    // 非正常退出时尝试重启
    if (code !== 0 && code !== null) {
      console.log('[Frank] Attempting to restart Python service in 3s...');
      setTimeout(spawnPython, 3000);
    }
  });

  pythonProcess.on('error', (err) => {
    console.error('[Frank] Failed to spawn Python process:', err.message);
    pythonProcess = null;
  });
}

// ─── WebSocket 连接管理 ─────────────────────────────────
function readPortFile() {
  try {
    const portPath = path.join(__dirname, '..', '..', '..', '.frank_port');
    if (fs.existsSync(portPath)) {
      const port = parseInt(fs.readFileSync(portPath, 'utf-8').trim(), 10);
      if (port > 0) return port;
    }
  } catch (_) { /* ignore */ }
  return null;
}

function connectWebSocket() {
  if (wsConnection && wsConnection.readyState === WebSocket.OPEN) return;

  const port = readPortFile() || config.websocket?.port || 8765;
  const url = `ws://localhost:${port}`;

  console.log(`[Frank] Connecting to Python service at ${url}...`);
  wsConnection = new WebSocket(url);

  wsConnection.on('open', () => {
    console.log('[Frank] WebSocket connected');
    wsReconnectAttempt = 0;
    startHeartbeat();
  });

  wsConnection.on('message', (data) => {
    try {
      const msg = JSON.parse(data.toString());
      handleMessage(msg);
    } catch (e) {
      console.error('[Frank] Failed to parse WebSocket message:', e);
    }
  });

  wsConnection.on('close', () => {
    console.log('[Frank] WebSocket disconnected');
    wsConnection = null;
    stopHeartbeat();
    scheduleReconnect();
  });

  wsConnection.on('error', (err) => {
    console.error('[Frank] WebSocket error:', err.message);
  });
}

function scheduleReconnect() {
  if (wsReconnectTimer) return;
  let safeBackoff = config.websocket?.reconnect_backoff;
  if (!Array.isArray(safeBackoff) || safeBackoff.length === 0) {
    console.warn('[Frank] Invalid reconnect_backoff config, using defaults');
    safeBackoff = [1, 2, 4, 8, 16, 30];
  }
  const delayMs = (safeBackoff[Math.min(wsReconnectAttempt, safeBackoff.length - 1)] || 1) * 1000;
  console.log(`[Frank] Reconnecting in ${delayMs / 1000}s (attempt ${wsReconnectAttempt + 1})...`);
  wsReconnectTimer = setTimeout(() => {
    wsReconnectTimer = null;
    wsReconnectAttempt++;
    connectWebSocket();
  }, delayMs);
}

let heartbeatInterval = null;

function startHeartbeat() {
  stopHeartbeat();
  heartbeatInterval = setInterval(() => {
    if (wsConnection && wsConnection.readyState === WebSocket.OPEN) {
      sendMessage({ type: 'ping' });
    }
  }, (config.websocket?.heartbeat_interval || 5) * 1000);
}

function stopHeartbeat() {
  if (heartbeatInterval) {
    clearInterval(heartbeatInterval);
    heartbeatInterval = null;
  }
}

// ─── 消息处理 ───────────────────────────────────────────
function sendMessage(msg) {
  if (!wsConnection || wsConnection.readyState !== WebSocket.OPEN) {
    console.warn('[Frank] Cannot send message: WebSocket not connected');
    return;
  }
  msg.id = msg.id || generateUUID();
  msg.timestamp = new Date().toISOString();
  wsConnection.send(JSON.stringify(msg));
}

function generateUUID() {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

function handleMessage(msg) {
  switch (msg.type) {
    case 'pong':
      break; // 心跳响应，无需处理
    case 'server.ready':
      console.log('[Frank] Server ready:', JSON.stringify(msg.payload));
      break;
    case 'state.changed':
      currentState = { name: msg.payload.to, timeInState: 0 };
      if (mainWindow) {
        mainWindow.webContents.send('state:changed', msg.payload);
      }
      console.log(`[Frank] State: ${msg.payload.from} → ${msg.payload.to} (${msg.payload.trigger})`);
      break;
    case 'state.current':
      currentState = { name: msg.payload.state, timeInState: msg.payload.time_in_state || 0 };
      if (mainWindow) {
        mainWindow.webContents.send('state:current', msg.payload);
      }
      break;
    case 'camera.face_detected':
      if (mainWindow) mainWindow.webContents.send('camera:face_detected', msg.payload);
      break;
    case 'camera.face_lost':
      if (mainWindow) mainWindow.webContents.send('camera:face_lost', msg.payload);
      break;
    case 'mic.voice_start':
      if (mainWindow) mainWindow.webContents.send('mic:voice_start', msg.payload);
      break;
    case 'mic.voice_end':
      if (mainWindow) mainWindow.webContents.send('mic:voice_end', msg.payload);
      break;
    case 'mic.wake_word':
      if (mainWindow) mainWindow.webContents.send('mic:wake_word', msg.payload);
      console.log(`[Frank] Wake word detected! Confidence: ${msg.payload.confidence}`);
      break;
    // Phase 2: Identity events
    case 'identity.confirmed':
      currentIdentity = msg.payload;
      if (mainWindow) mainWindow.webContents.send('identity:confirmed', msg.payload);
      console.log(`[Frank] Identity confirmed: ${msg.payload.display_name} (${msg.payload.role})`);
      break;
    case 'identity.changing':
      if (mainWindow) mainWindow.webContents.send('identity:changing', msg.payload);
      break;
    case 'identity.unknown':
      if (mainWindow) mainWindow.webContents.send('identity:unknown', msg.payload);
      break;
    case 'identity.current':
      currentIdentity = msg.payload;
      if (mainWindow) mainWindow.webContents.send('identity:current', msg.payload);
      break;
    // Phase 2: Member events
    case 'member.list':
    case 'member.pending':
    case 'member.identified':
    case 'member.deleted':
    case 'member.register_started':
    case 'member.register_info_ok':
    case 'member.register_cancelled':
      if (mainWindow) mainWindow.webContents.send(msg.type, msg.payload);
      break;
    // Phase 2: Role / Settings events
    case 'role.list':
    case 'role.info':
    case 'settings.current':
    case 'settings.updated':
      if (mainWindow) mainWindow.webContents.send(msg.type, msg.payload);
      break;
    case 'error':
      console.error(`[Frank] Error from Python: [${msg.payload.code}] ${msg.payload.message}`);
      if (mainWindow) mainWindow.webContents.send('error', msg.payload);
      break;
    // Phase 3: Chat / Conversation events
    case 'chat.sub_state':
    case 'chat.user_message':
    case 'chat.assistant_message':
    case 'chat.listening':
      if (mainWindow) mainWindow.webContents.send(msg.type, msg.payload);
      break;
    // Phase 3: STT / LLM / TTS events
    case 'stt.transcription':
    case 'llm.token':
    case 'llm.response':
    case 'tts.start':
    case 'tts.complete':
    case 'tts.unavailable':
      if (mainWindow) mainWindow.webContents.send(msg.type, msg.payload);
      break;
    // Phase 4: Multi-person / Task / Skill events
    case 'multi_person.state':
    case 'multi_person.join':
    case 'multi_person.leave':
    case 'multi_person.status':
    case 'task.list':
    case 'task.list_all':
    case 'task.get':
    case 'skill.list':
    case 'skill.result':
      if (mainWindow) mainWindow.webContents.send(msg.type, msg.payload);
      break;
    // Phase 5: Gesture events
    case 'gesture.detected':
    case 'gesture.registered':
    case 'gesture.bound':
    case 'gesture.unbound':
    case 'gesture.bindings_list':
    case 'gesture.custom_list':
    case 'gesture.deleted':
      if (mainWindow) mainWindow.webContents.send(msg.type, msg.payload);
      break;
    // 预览帧 → 预览窗口
    case 'preview.frame':
    case 'preview.detections':
    case 'preview.audio_spectrum':
      if (previewWindow && !previewWindow.isDestroyed()) {
        previewWindow.webContents.send(msg.type, msg.payload);
      }
      break;
    // 设备状态 → 主窗口
    case 'device.status':
      if (mainWindow) mainWindow.webContents.send('device:status', msg.payload);
      break;
    // 通知事件 → 主窗口
    case 'notification':
    // 任务事件 → 主窗口
    case 'task.updated':
    case 'task.completed':
    case 'task.failed':
      if (mainWindow) mainWindow.webContents.send(msg.type, msg.payload);
      break;
    default:
      console.log(`[Frank] Unhandled message type: ${msg.type}`);
  }
}

// ─── 窗口管理 ───────────────────────────────────────────
function createWindow() {
  const { x, y } = config.window || {};
  const WINDOW_WIDTH = 800;
  const WINDOW_HEIGHT = 600;

  mainWindow = new BrowserWindow({
    width: WINDOW_WIDTH,
    height: WINDOW_HEIGHT,
    minWidth: 500,
    minHeight: 400,
    x,
    y,
    frame: false,
    transparent: false,
    backgroundColor: '#0a0a0c',
    resizable: true,
    skipTaskbar: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  // 首次启动居中
  if (!x && !y) {
    mainWindow.center();
  }

  mainWindow.loadFile(path.join(__dirname, '..', 'renderer', 'index.html'));

  mainWindow.on('close', (event) => {
    if (app.isQuitting) return;
    if (config.app?.minimize_to_tray !== false) {
      event.preventDefault();
      mainWindow.hide();
    }
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  // 记住窗口位置
  mainWindow.on('move', saveWindowBounds);
  mainWindow.on('resize', saveWindowBounds);
}

function saveWindowBounds() {
  if (!mainWindow) return;
  const bounds = mainWindow.getBounds();
  // 仅当 window 状态正常时保存
  if (!mainWindow.isMaximized() && !mainWindow.isMinimized()) {
    // 保存到内存中的 config，后续可考虑持久化到 electron-store
    config.window = { ...config.window, ...bounds };
  }
}

// ─── 预览窗口 ───────────────────────────────────────────
function createPreviewWindow() {
  if (previewWindow && !previewWindow.isDestroyed()) {
    previewWindow.focus();
    return;
  }
  previewWindow = new BrowserWindow({
    width: 1280,
    height: 720,
    minWidth: 800,
    minHeight: 450,
    frame: false,
    backgroundColor: '#0a0a0c',
    resizable: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  previewWindow.loadFile(path.join(__dirname, '..', 'renderer', 'preview.html'));
  previewWindow.on('closed', () => {
    previewWindow = null;
    sendMessage({ type: 'preview.close' });
  });
  sendMessage({ type: 'preview.open' });
}

function closePreviewWindow() {
  if (previewWindow && !previewWindow.isDestroyed()) {
    previewWindow.destroy();  // closed event handler sends 'preview.close'
    // previewWindow = null handled in 'closed' event
  }
}

// ─── 系统托盘 ───────────────────────────────────────────
function createTray() {
  // 创建 16x16 托盘图标 (简单的绿色圆点 PNG，base64)
  const iconData = Buffer.from(
    'iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAA' +
    'OklEQVQ4y2Ng+M9AAWBiYGBgYGBg+M9AAWBiYGBgYGBg+M9A' +
    'AWBiYGBgYGBg+M9AAWBiYGBgYGBg+M9AAWBiYGBgYGBg+M9A' +
    'AWBi+M8AAJqTAQEJhVK+AAAAAElFTkSuQmCC',
    'base64'
  );
  const icon = nativeImage.createFromBuffer(iconData);

  tray = new Tray(icon);
  tray.setToolTip('Frank (弗兰克)');

  const contextMenu = Menu.buildFromTemplate([
    {
      label: '显示/隐藏窗口',
      click: () => {
        if (mainWindow && mainWindow.isVisible()) {
          mainWindow.hide();
        } else if (mainWindow) {
          mainWindow.show();
          mainWindow.focus();
        }
      },
    },
    { type: 'separator' },
    {
      label: `状态: ${currentState.name}`,
      enabled: false,
    },
    { type: 'separator' },
    {
      label: '设置',
      enabled: false,
    },
    {
      label: '退出',
      click: () => {
        app.isQuitting = true;
        app.quit();
      },
    },
  ]);

  tray.setContextMenu(contextMenu);

  tray.on('double-click', () => {
    if (mainWindow) {
      if (mainWindow.isVisible()) {
        mainWindow.hide();
      } else {
        mainWindow.show();
        mainWindow.focus();
      }
    }
  });

  // 定期更新托盘菜单中的状态
  trayUpdateInterval = setInterval(() => {
    if (tray) {
      const updatedMenu = Menu.buildFromTemplate([
        {
          label: '显示/隐藏窗口',
          click: () => {
            if (mainWindow && mainWindow.isVisible()) {
              mainWindow.hide();
            } else if (mainWindow) {
              mainWindow.show();
              mainWindow.focus();
            }
          },
        },
        { type: 'separator' },
        {
          label: `状态: ${currentState.name}`,
          enabled: false,
        },
        { type: 'separator' },
        {
          label: '设置',
          enabled: false,
        },
        {
          label: '退出',
          click: () => {
            app.isQuitting = true;
            app.quit();
          },
        },
      ]);
      tray.setContextMenu(updatedMenu);
    }
  }, 5000);
}

// ─── 应用生命周期 ───────────────────────────────────────
app.on('ready', async () => {
  console.log('[Frank] Application starting...');

  // 加载配置
  config = loadConfig();

  // 开机自启
  if (config.app?.auto_start !== false) {
    setAutoStart(true);
  }

  // 创建窗口
  createWindow();

  // 创建托盘
  createTray();

  // 启动 Python 推理服务（就绪后自动连接 WebSocket）
  spawnPython();

  // 注册 IPC 处理器
  createIPC(mainWindow, {
    sendMessage,
    getState: () => currentState,
    createPreviewWindow,
    closePreviewWindow,
  });
});

app.on('window-all-closed', () => {
  // 不退出应用，保持在托盘运行
});

app.on('before-quit', () => {
  app.isQuitting = true;
  stopHeartbeat();
  if (trayUpdateInterval) {
    clearInterval(trayUpdateInterval);
    trayUpdateInterval = null;
  }
  if (wsConnection) {
    wsConnection.close();
  }
  if (previewWindow && !previewWindow.isDestroyed()) {
    previewWindow.destroy();
    previewWindow = null;
  }
  if (pythonProcess) {
    console.log('[Frank] Stopping Python service...');
    pythonProcess.kill();
    pythonProcess = null;
  }
  if (wsReconnectTimer) {
    clearTimeout(wsReconnectTimer);
  }
});

app.on('activate', () => {
  if (mainWindow) {
    mainWindow.show();
  }
});
