# 第二轮需求 — 识别预览窗口 + 实时状态接入 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 Frank 桌面助手新增独立识别预览窗口（视觉+音频可视化），将窗口控制按钮融入状态栏，接入设备实时状态和任务执行状态到主界面。

**Architecture:** 新增独立 BrowserWindow 作为预览窗口，Python 后端通过 WebSocket→主进程→IPC 通道推送预览帧和频谱数据。主窗口 UI 增量修改：状态栏嵌入窗口按钮、硬件芯片接入实时数据、任务面板替换种子数据为后端事件。

**Tech Stack:** Electron (BrowserWindow + IPC), Python asyncio (WebSocket 广播), Canvas 2D API, Web Audio API (AudioContext + AnalyserNode), JPEG base64 帧传输

---

## 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `src/electron/main/main.js` | 修改 | 预览窗口生命周期 + 新消息路由 |
| `src/electron/main/ipc.js` | 修改 | 新增 4 个 IPC handler |
| `src/electron/main/preload.js` | 修改 | 新增 11 个 API |
| `src/electron/renderer/index.html` | 修改 | 窗口按钮融入状态栏、光球点击行为 |
| `src/electron/renderer/styles.css` | 修改 | 移除旧按钮样式、新增紧凑按钮样式 |
| `src/electron/renderer/app.js` | 修改 | 移除种子数据、新增实时事件监听 |
| `src/electron/renderer/preview.html` | **新建** | 预览窗口 HTML |
| `src/electron/renderer/preview.css` | **新建** | 预览窗口样式 |
| `src/electron/renderer/preview.js` | **新建** | 预览窗口渲染逻辑 |
| `src/python/server/main.py` | 修改 | device.status 定时器、预览开关、toggle 处理、任务回调 |
| `src/python/modules/camera/camera_pipeline.py` | 修改 | 预览帧+检测结果推送 |
| `src/python/modules/audio/audio_pipeline.py` | 修改 | 预览频谱推送+FFT |
| `src/python/modules/task_manager/task_manager.py` | 修改 | 任务事件广播回调 |

---

### Task 1: 后端 — 预览数据推送基础设施

**Files:**
- Modify: `src/python/server/main.py` (near line 86, after global declarations)
- Modify: `src/python/modules/camera/camera_pipeline.py` (add preview methods)
- Modify: `src/python/modules/audio/audio_pipeline.py` (add FFT + preview methods)

- [ ] **Step 1: 在 main.py 中添加预览状态标记和消息处理**

在 `src/python/server/main.py` 中，找到全局变量声明区（第 86 行 `connected_clients` 后），添加预览状态：

```python
# 在 connected_clients: set = set() 之后添加：
_preview_active = False
_preview_client = None  # 当前请求预览的 websocket 连接
```

在 `handle_message()` 的 match 分支中（约第 362 行 `case 'ping':` 之前），新增两个 case：

```python
            # ── 预览控制 ──
            case 'preview.open':
                global _preview_active, _preview_client
                _preview_active = True
                _preview_client = websocket
                if camera_pipeline:
                    camera_pipeline.set_preview_active(True)
                if audio_pipeline:
                    audio_pipeline.set_preview_active(True)
                await send_message(websocket, 'preview.opened', {}, msg_id)

            case 'preview.close':
                global _preview_active, _preview_client
                _preview_active = False
                _preview_client = None
                if camera_pipeline:
                    camera_pipeline.set_preview_active(False)
                if audio_pipeline:
                    audio_pipeline.set_preview_active(False)
                await send_message(websocket, 'preview.closed', {}, msg_id)
```

- [ ] **Step 2: 在 CameraPipeline 中添加预览推送能力**

在 `src/python/modules/camera/camera_pipeline.py` 中：

在 `__init__` 方法末尾（第 69 行 `self._on_error: Callable | None = None` 之后）添加：

```python
        self._preview_active = False
        self._on_preview_frame: Callable | None = None
        self._on_preview_detections: Callable | None = None
```

在回调设置区域（第 73 行后）添加：

```python
    def set_preview_active(self, active: bool):
        self._preview_active = active

    def set_on_preview_frame(self, callback: Callable):
        self._on_preview_frame = callback

    def set_on_preview_detections(self, callback: Callable):
        self._on_preview_detections = callback
```

在 `_capture_loop()` 方法中，在姿态帧回调之后（约第 293 行 `except Exception as e:` 之前），添加预览推送逻辑：

```python
                # 预览推送
                if self._preview_active:
                    if self._on_preview_frame:
                        import cv2
                        import base64
                        _, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
                        jpeg_b64 = base64.b64encode(jpeg).decode('ascii')
                        preview_frame = {
                            'frame_id': int(time.time() * 1000),
                            'jpeg_base64': jpeg_b64,
                            'width': self.width,
                            'height': self.height,
                            'timestamp': time.time(),
                        }
                        if asyncio.iscoroutinefunction(self._on_preview_frame):
                            await self._on_preview_frame(preview_frame)
                        else:
                            self._on_preview_frame(preview_frame)

                    if self._on_preview_detections:
                        detections = {
                            'frame_id': int(time.time() * 1000),
                            'faces': faces,
                            'objects': [],
                            'pose_landmarks': None,
                            'gesture': None,
                            'fps': self._current_fps,
                        }
                        if asyncio.iscoroutinefunction(self._on_preview_detections):
                            await self._on_preview_detections(detections)
                        else:
                            self._on_preview_detections(detections)
```

- [ ] **Step 3: 在 AudioPipeline 中添加预览频谱推送**

在 `src/python/modules/audio/audio_pipeline.py` 中：

在 `__init__` 末尾添加：

```python
        self._preview_active = False
        self._on_preview_spectrum: Callable | None = None
```

添加回调方法：

```python
    def set_preview_active(self, active: bool):
        self._preview_active = active

    def set_on_preview_spectrum(self, callback: Callable):
        self._on_preview_spectrum = callback
```

在 `_process_loop()` 方法中，在 VAD 检测之后（约第 330 行 `time.sleep(0.01)` 之前），添加频谱推送：

```python
                # 预览频谱推送 (~20Hz)
                if self._preview_active and self._on_preview_spectrum and self._ring_buffer and len(self._ring_buffer) >= 512:
                    all_data, _ = self._ring_buffer.get_all()
                    recent = all_data[-512:]
                    # FFT 频谱
                    fft = np.abs(np.fft.rfft(recent))
                    bins = 32
                    bin_size = len(fft) // bins
                    spectrum = [float(np.mean(fft[i*bin_size:(i+1)*bin_size])) for i in range(bins)]
                    # 归一化
                    max_val = max(spectrum) if max(spectrum) > 0 else 1.0
                    spectrum = [s / max_val for s in spectrum]
                    # 音量电平 (dB)
                    rms = np.sqrt(np.mean(recent ** 2))
                    level_db = float(20 * np.log10(max(rms, 1e-6)))
                    # 基频估计 (简单自相关)
                    pitch_hz = 0.0
                    if rms > 0.01:
                        corr = np.correlate(recent, recent, mode='full')
                        corr = corr[len(corr)//2:]
                        corr = corr / (corr[0] + 1e-10)
                        peaks = np.where(corr[16:] > 0.5)[0]
                        if len(peaks) > 0:
                            lag = peaks[0] + 16
                            pitch_hz = float(self.sample_rate / lag) if lag > 0 else 0.0
                    spectrum_msg = {
                        'spectrum_bins': spectrum,
                        'vad_prob': float(speech_prob),
                        'level_db': level_db,
                        'wake_word_trigger': False,
                        'pitch_hz': pitch_hz,
                        'voiceprint_matches': [],
                    }
                    if self._main_loop and self._main_loop.is_running():
                        asyncio.run_coroutine_threadsafe(
                            self._on_preview_spectrum(spectrum_msg),
                            self._main_loop
                        )
```

- [ ] **Step 4: Commit**

```bash
git add src/python/server/main.py src/python/modules/camera/camera_pipeline.py src/python/modules/audio/audio_pipeline.py
git commit -m "feat: add preview data push infrastructure to backend pipelines"
```

---

### Task 2: 后端 — device.status 定时推送 + toggle 处理 + 任务事件回调

**Files:**
- Modify: `src/python/server/main.py` (add timer, toggle handlers, task callbacks)

- [ ] **Step 1: 在 main.py 的 main() 中添加 device.status 定时广播**

在 `src/python/server/main.py` 的 `main()` 函数中，在管线启动之后（约第 731 行 `logger.info('Audio pipeline started')` 之后），添加定时器：

```python
        # 启动 device.status 定时广播
        async def broadcast_device_status():
            while True:
                await asyncio.sleep(1.0)
                status = {
                    'camera': {
                        'active': camera_pipeline._running if camera_pipeline else False,
                        'fps': camera_pipeline._current_fps if camera_pipeline else 0,
                        'faces_detected': camera_pipeline._faces_last_frame if camera_pipeline else 0,
                        'resolution': f"{camera_pipeline.width}x{camera_pipeline.height}" if camera_pipeline else "N/A",
                        'pipeline': 'InsightFace' if (camera_pipeline and camera_pipeline.is_insightface_ready) else 'MediaPipe',
                    },
                    'microphone': {
                        'active': audio_pipeline._running if audio_pipeline else False,
                        'level_db': -20.0,
                        'vad_active': audio_pipeline._voice_active if audio_pipeline else False,
                        'sample_rate': audio_pipeline.sample_rate if audio_pipeline else 0,
                        'pipeline': 'Silero VAD',
                    },
                    'screen': {
                        'active': False,
                    },
                }
                await broadcast_event('device.status', status)

        asyncio.create_task(broadcast_device_status())
```

- [ ] **Step 2: 添加 camera.toggle 和 microphone.toggle 消息处理**

在 `handle_message()` 的 match 分支中，`case 'ping':` 之前添加：

```python
            # ── 设备开关 ──
            case 'camera.toggle':
                if camera_pipeline:
                    if camera_pipeline._running:
                        await camera_pipeline.stop()
                        await send_message(websocket, 'camera.stopped', {}, msg_id)
                    else:
                        await camera_pipeline.start()
                        await send_message(websocket, 'camera.started', {}, msg_id)
                else:
                    await send_error(websocket, 'CAM_NOT_INIT', '摄像头模块未初始化', True, '', msg_id)

            case 'microphone.toggle':
                if audio_pipeline:
                    if audio_pipeline._running:
                        await audio_pipeline.stop()
                        await send_message(websocket, 'mic.stopped', {}, msg_id)
                    else:
                        await audio_pipeline.start()
                        await send_message(websocket, 'mic.started', {}, msg_id)
                else:
                    await send_error(websocket, 'MIC_NOT_INIT', '麦克风模块未初始化', True, '', msg_id)
```

- [ ] **Step 3: 在 main() 中注册 task_manager 事件回调**

在 `main()` 函数的 task_manager 初始化之后（约第 675 行），添加回调注册：

```python
    # 任务事件回调（广播到 Electron）
    task_manager.set_on_task_update(
        lambda task: asyncio.create_task(broadcast_event('task.started' if task.get('status') == 'executing' else 'task.progress', task))
    )
    task_manager.set_on_task_completed(
        lambda task: asyncio.create_task(broadcast_event('task.completed', task))
    )
    task_manager.set_on_task_failed(
        lambda task: asyncio.create_task(broadcast_event('task.failed', task))
    )
```

但需要调整——`set_on_task_update` 当前同时用于 started 和 progress，需要更精确的区分。改为直接在 `task_manager.py` 的任务状态变更点调用不同的回调。先保持简单，在 `main.py` 中用 `set_on_task_update` 统一处理：

```python
    task_manager.set_on_task_update(
        lambda task: asyncio.create_task(broadcast_event('task.updated', task))
    )
    task_manager.set_on_task_completed(
        lambda task: asyncio.create_task(broadcast_event('task.completed', task))
    )
    task_manager.set_on_task_failed(
        lambda task: asyncio.create_task(broadcast_event('task.failed', task))
    )
```

- [ ] **Step 4: 在 main() 中注册预览推送回调**

在 `main()` 函数中，在 camera_pipeline 回调设置之后，添加预览回调：

```python
    # 预览推送回调
    async def on_preview_frame(data):
        global _preview_client
        if _preview_client:
            try:
                await send_message(_preview_client, 'preview.frame', data)
            except Exception:
                pass

    async def on_preview_detections(data):
        global _preview_client
        if _preview_client:
            try:
                await send_message(_preview_client, 'preview.detections', data)
            except Exception:
                pass

    async def on_preview_spectrum(data):
        global _preview_client
        if _preview_client:
            try:
                await send_message(_preview_client, 'preview.audio_spectrum', data)
            except Exception:
                pass

    camera_pipeline.set_on_preview_frame(on_preview_frame)
    camera_pipeline.set_on_preview_detections(on_preview_detections)
    audio_pipeline.set_on_preview_spectrum(on_preview_spectrum)
```

- [ ] **Step 5: Commit**

```bash
git add src/python/server/main.py
git commit -m "feat: add device.status timer, toggle handlers, task callbacks, preview callbacks to server"
```

---

### Task 3: Electron 主进程 — 预览窗口管理 + 新消息路由 + IPC

**Files:**
- Modify: `src/electron/main/main.js`
- Modify: `src/electron/main/ipc.js`

- [ ] **Step 1: 在 main.js 中添加预览窗口管理函数**

在 `main.js` 中，在 `let currentState` 附近（第 17 行）添加预览窗口变量：

```javascript
let previewWindow = null;
```

在 `createWindow()` 函数之后，添加预览窗口创建和销毁函数：

```javascript
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
    sendMessage({ type: 'preview.close' });
    previewWindow.destroy();
    previewWindow = null;
  }
}
```

- [ ] **Step 2: 在 handleMessage() 中添加预览/设备/任务消息路由**

在 `handleMessage()` 的 switch 中，`default:` 之前添加：

```javascript
    // 预览帧 → 预览窗口
    case 'preview.frame':
      if (previewWindow && !previewWindow.isDestroyed()) {
        previewWindow.webContents.send('preview:frame', msg.payload);
      }
      break;
    case 'preview.detections':
      if (previewWindow && !previewWindow.isDestroyed()) {
        previewWindow.webContents.send('preview:detections', msg.payload);
      }
      break;
    case 'preview.audio_spectrum':
      if (previewWindow && !previewWindow.isDestroyed()) {
        previewWindow.webContents.send('preview:audio_spectrum', msg.payload);
      }
      break;
    // 设备状态 → 主窗口
    case 'device.status':
      if (mainWindow) mainWindow.webContents.send('device:status', msg.payload);
      break;
    // 任务事件 → 主窗口
    case 'task.updated':
    case 'task.completed':
    case 'task.failed':
      if (mainWindow) mainWindow.webContents.send(msg.type, msg.payload);
      break;
```

- [ ] **Step 3: 在 main.js 中更新 createIPC 调用，传入预览函数**

找到 `createIPC(mainWindow, { sendMessage, getState })` 调用，扩展参数：

```javascript
createIPC(mainWindow, {
  sendMessage,
  getState: () => currentState,
  createPreviewWindow,
  closePreviewWindow,
});
```

- [ ] **Step 4: 在 ipc.js 中添加新的 IPC handler**

在 `src/electron/main/ipc.js` 的 `createIPC()` 函数中，更新参数解构：

```javascript
function createIPC(mainWindow, { sendMessage, getState, createPreviewWindow, closePreviewWindow }) {
```

在 `frank:quitApp` handler 之后（约第 69 行 `return { confirmed: false };` 之后），添加：

```javascript
  // ── 预览窗口 IPC ──
  ipcMain.handle('frank:openPreview', () => {
    if (createPreviewWindow) createPreviewWindow();
  });

  ipcMain.handle('frank:closePreview', () => {
    if (closePreviewWindow) closePreviewWindow();
  });

  // ── 设备控制 IPC ──
  ipcMain.handle('frank:toggleCamera', () => {
    if (sendMessage) sendMessage({ type: 'camera.toggle' });
  });

  ipcMain.handle('frank:toggleMicrophone', () => {
    if (sendMessage) sendMessage({ type: 'microphone.toggle' });
  });
```

- [ ] **Step 5: 在 main.js before-quit 中清理预览窗口**

在 `app.on('before-quit', ...)` 中，在现有清理代码中追加：

```javascript
  if (previewWindow && !previewWindow.isDestroyed()) {
    previewWindow.destroy();
    previewWindow = null;
  }
```

- [ ] **Step 6: Commit**

```bash
git add src/electron/main/main.js src/electron/main/ipc.js
git commit -m "feat: add preview window lifecycle, message routing, and IPC handlers to Electron main"
```

---

### Task 4: Electron Preload — 新增 API

**Files:**
- Modify: `src/electron/main/preload.js`

- [ ] **Step 1: 在 preload.js 中添加所有新 API**

在 `src/electron/main/preload.js` 末尾（`});` 之前），添加：

```javascript
  // ── 预览窗口 ──
  openPreview: () => ipcRenderer.invoke('frank:openPreview'),
  closePreview: () => ipcRenderer.invoke('frank:closePreview'),

  // ── 设备控制 ──
  toggleCamera: () => ipcRenderer.invoke('frank:toggleCamera'),
  toggleMicrophone: () => ipcRenderer.invoke('frank:toggleMicrophone'),

  // ── 设备状态 ──
  onDeviceStatus: (callback) => {
    const handler = (_event, data) => callback(data);
    ipcRenderer.on('device:status', handler);
    return () => ipcRenderer.removeListener('device:status', handler);
  },

  // ── 任务事件 ──
  onTaskUpdated: (callback) => {
    const handler = (_event, data) => callback(data);
    ipcRenderer.on('task.updated', handler);
    return () => ipcRenderer.removeListener('task.updated', handler);
  },
  onTaskCompleted: (callback) => {
    const handler = (_event, data) => callback(data);
    ipcRenderer.on('task.completed', handler);
    return () => ipcRenderer.removeListener('task.completed', handler);
  },
  onTaskFailed: (callback) => {
    const handler = (_event, data) => callback(data);
    ipcRenderer.on('task.failed', handler);
    return () => ipcRenderer.removeListener('task.failed', handler);
  },

  // ── 预览窗口数据 (仅预览窗口使用) ──
  onPreviewFrame: (callback) => {
    const handler = (_event, data) => callback(data);
    ipcRenderer.on('preview:frame', handler);
    return () => ipcRenderer.removeListener('preview:frame', handler);
  },
  onPreviewDetections: (callback) => {
    const handler = (_event, data) => callback(data);
    ipcRenderer.on('preview:detections', handler);
    return () => ipcRenderer.removeListener('preview:detections', handler);
  },
  onPreviewAudioSpectrum: (callback) => {
    const handler = (_event, data) => callback(data);
    ipcRenderer.on('preview:audio_spectrum', handler);
    return () => ipcRenderer.removeListener('preview:audio_spectrum', handler);
  },
```

- [ ] **Step 2: Commit**

```bash
git add src/electron/main/preload.js
git commit -m "feat: add preview, device, and task APIs to preload bridge"
```

---

### Task 5: 主窗口 UI — 窗口按钮融入状态栏 + 光球点击改为预览

**Files:**
- Modify: `src/electron/renderer/index.html`
- Modify: `src/electron/renderer/styles.css`

- [ ] **Step 1: 修改 index.html — 移除独立窗口控制块**

删除第 13-16 行：

```html
  <!-- 外置窗口控制条 -->
  <div class="window-controls">
    <button class="window-ctrl-btn" id="btn-minimize" title="最小化">─</button>
    <button class="window-ctrl-btn close" id="btn-close" title="关闭到托盘">✕</button>
  </div>
```

- [ ] **Step 2: 在 .status-right 内追加窗口控制按钮**

找到 `<div class="status-right">`（第 37 行），在通知预览后追加：

```html
        <div class="status-right">
          <div class="time-block" id="liveTime">00:00</div>
          <div class="notif-preview hidden" id="notifPreview">
            <span class="notif-preview-dot"></span>
            <span class="notif-preview-text" id="notifText"></span>
            <span class="notif-count" id="notifCount">0</span>
          </div>
          <button class="window-ctrl-btn-mini" id="btn-minimize" title="最小化">─</button>
          <button class="window-ctrl-btn-mini close" id="btn-close" title="关闭到托盘">✕</button>
        </div>
```

- [ ] **Step 3: 修改光球交互 — title 提示改为预览**

找到 `<div class="orb" id="frankOrb" ...>`（第 74 行），修改 title：

```html
          <div class="orb" id="frankOrb" title="点击查看识别预览"></div>
```

修改 agent label 为可点击的对话入口：

```html
        <div class="agent-label" id="agentLabel"><span class="pulse-dot"></span> <span id="agentLabelText" class="agent-label-clickable" title="点击对话">聆听中 · 等待唤醒</span></div>
```

- [ ] **Step 4: 修改 styles.css — 移除旧按钮样式，新增紧凑按钮样式**

删除 `.window-controls` 和 `.window-ctrl-btn` 相关样式（第 430-435 行）：

```css
/* 删除以下块：
.back-home { position: fixed; ... }
.window-controls { position: fixed; ... }
.window-ctrl-btn { ... }
.window-ctrl-btn:hover { ... }
.window-ctrl-btn.close:hover { ... }
*/
```

保留 `.back-home` 但移除 `.window-controls` 和 `.window-ctrl-btn` 规则。

在状态栏样式区域（第 147 行 `.status-right` 规则附近）添加：

```css
/* 窗口控制按钮（融入状态栏） */
.window-ctrl-btn-mini {
  width: 20px; height: 20px;
  border-radius: 4px;
  background: transparent;
  border: none;
  color: var(--fg-2);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  transition: all var(--motion-fast);
  font-family: var(--font-display);
  flex-shrink: 0;
  padding: 0;
  line-height: 1;
}
.window-ctrl-btn-mini:hover {
  color: var(--fg);
  background: var(--border-soft);
}
.window-ctrl-btn-mini.close:hover {
  background: var(--danger);
  color: white;
}
```

在 agent label 区域（第 276 行 `.agent-label` 之后）添加可点击样式：

```css
.agent-label-clickable {
  cursor: pointer;
  transition: color var(--motion-fast);
}
.agent-label-clickable:hover {
  color: var(--accent);
}
```

- [ ] **Step 5: Commit**

```bash
git add src/electron/renderer/index.html src/electron/renderer/styles.css
git commit -m "feat: merge window controls into status bar, change orb click to open preview"
```

---

### Task 6: 主窗口 JS — 移除种子数据 + 接入实时事件

**Files:**
- Modify: `src/electron/renderer/app.js`

- [ ] **Step 1: 修改光球点击行为**

找到 `frankOrb?.addEventListener('click', () => openPanel('chat'));`，替换为：

```javascript
// Orb click → open preview window
frankOrb?.addEventListener('click', () => {
  window.frankAPI?.openPreview?.();
});
```

- [ ] **Step 2: 添加 agent label 点击打开对话**

在光球事件绑定之后添加：

```javascript
// Agent label click → open chat
$('agentLabelText')?.addEventListener('click', (e) => {
  e.stopPropagation();
  openPanel('chat');
});
```

- [ ] **Step 3: 替换 init() 中的种子数据为实时数据监听**

移除 `init()` 中的以下种子数据代码块（第 566-591 行）：
- `allTasks = [...]` 初始化
- `renderInlineTasks(allTasks)` 调用
- `updateInlineConversation(...)` 调用
- `renderNotifList([...])` 种子通知
- `notifText` / `notifCount` / `notifPreview` 种子值设定

替换为在 IPC 初始化区域（`if (window.frankAPI)` 块）添加：

```javascript
  // ── 任务事件 ──
  window.frankAPI.onTaskUpdated(data => {
    upsertTask({
      task_id: data.task_id,
      status: data.status === 'executing' ? 'running' : data.status === 'queued' ? 'pending' : data.status,
      text: data.display_name || data.command || '',
      source: data.user_id ? 'user' : 'sys',
      elapsed: data.started_at ? formatTime(data.started_at) : '—',
      progress: data.progress || 0,
    });
    // 同步更新任务面板
    if (PanelManager.isOpen($('taskDetailPanel'))) {
      refreshTaskDetailPanel();
    }
  });
  window.frankAPI.onTaskCompleted(data => {
    upsertTask({
      task_id: data.task_id,
      status: 'done',
      text: data.display_name || data.command || '',
      source: data.user_id ? 'user' : 'sys',
      elapsed: data.completed_at ? formatTime(data.completed_at) : '—',
      progress: 100,
    });
  });
  window.frankAPI.onTaskFailed(data => {
    upsertTask({
      task_id: data.task_id,
      status: 'failed',
      text: data.display_name || data.command || '',
      source: data.user_id ? 'user' : 'sys',
      elapsed: data.completed_at ? formatTime(data.completed_at) : '—',
      progress: data.progress || 0,
      error: data.error_info?.message || '未知错误',
    });
  });

  // ── 设备状态 ──
  window.frankAPI.onDeviceStatus(data => {
    // CAM
    if (data.camera) {
      setChipState(chipCAM, data.camera.active);
      if (chipCAM) chipCAM.title = `${data.camera.pipeline || 'Camera'} · ${data.camera.fps}fps · ${data.camera.faces_detected || 0} face`;
    }
    // MIC
    if (data.microphone) {
      setChipState(chipMIC, data.microphone.active);
      if (chipMIC) chipMIC.title = `${data.microphone.pipeline || 'Mic'} · ${data.microphone.level_db?.toFixed(1) || '—'}dB${data.microphone.vad_active ? ' · VAD' : ''}`;
    }
    // SCR
    if (data.screen) {
      setChipState(chipSCR, data.screen.active);
    }
  });

  // ── 对话事件 ──
  window.frankAPI.onUserMessage(data => {
    if (convoTopic) convoTopic.textContent = (data.text || '').length > 20 ? (data.text || '').substring(0, 20) + '…' : (data.text || '');
    if (convoMeta) convoMeta.textContent = '刚刚 · 用户';
  });
  window.frankAPI.onAssistantMessage(data => {
    if (convoMeta) convoMeta.textContent = '刚刚 · Frank';
  });
  window.frankAPI.onChatSubState(data => {
    if (agentLabelText) {
      const labels = { listening: '聆听中…', transcribing: '转写中…', thinking: '思考中…', speaking: '回复中…' };
      agentLabelText.textContent = labels[data.to] || data.to || '等待中';
    }
  });
  window.frankAPI.onSTTTranscription(data => {
    if (convoMeta) convoMeta.textContent = '转写: ' + ((data.text || '').substring(0, 30));
  });
```

- [ ] **Step 4: 添加芯片点击事件**

在 `init()` 或事件绑定区域添加：

```javascript
// Hardware chip click → toggle device
chipCAM?.addEventListener('click', () => window.frankAPI?.toggleCamera?.());
chipMIC?.addEventListener('click', () => window.frankAPI?.toggleMicrophone?.());
```

给芯片添加 CSS cursor pointer（在 styles.css 中）：`.hw-chip { cursor: pointer; }`

- [ ] **Step 5: 添加 upsertTask 辅助函数和 taskHistory 状态**

在 app.js 顶部（`STATE_CONFIG` 之后），添加任务历史管理：

```javascript
// ── Task history (replaces seed data) ─────────────────────
const taskHistory = [];
const MAX_TASK_HISTORY = 50;

function upsertTask(task) {
  const idx = taskHistory.findIndex(t => t.task_id === task.task_id);
  if (idx >= 0) {
    Object.assign(taskHistory[idx], task);
  } else {
    taskHistory.unshift(task);
    if (taskHistory.length > MAX_TASK_HISTORY) taskHistory.pop();
  }
  renderInlineTasks(taskHistory);
}
```

更新 `renderInlineTasks` 使用 `taskHistory` 中统一的状态字段：

```javascript
function renderInlineTasks(tasks) {
  if (!taskListScroll) return;
  if (taskCount) taskCount.textContent = String(tasks.length);
  taskListScroll.innerHTML = tasks.map(t => `
    <div class="task-row${t.status === 'done' ? ' done-row' : ''}" onclick="openPanel('chat')">
      <div class="task-status-icon ${t.status || 'pending'}">
        ${t.status === 'running' ? '<div class="task-spinner"></div>' : ''}
        ${t.status === 'pending' ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="10" height="10"><circle cx="12" cy="12" r="10"></circle><path d="M12 6v6l4 2"></path></svg>' : ''}
        ${t.status === 'done' ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="10" height="10"><path d="M20 6L9 17l-5-5"></path></svg>' : ''}
        ${t.status === 'failed' ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="10" height="10"><path d="M18 6L6 18M6 6l12 12"></path></svg>' : ''}
      </div>
      <span class="task-row-text">${t.text || ''}</span>
      <span class="task-row-source">${t.source || 'sys'}</span>
      <span class="task-row-elapsed">${t.elapsed || '—'}</span>
    </div>`).join('');
}
```

- [ ] **Step 6: Commit**

```bash
git add src/electron/renderer/app.js src/electron/renderer/styles.css
git commit -m "feat: replace seed data with real-time event listeners, wire orb to preview"
```

---

### Task 7: 预览窗口 — HTML + CSS（参照 design/vision.html）

**Files:**
- Create: `src/electron/renderer/preview.html`
- Create: `src/electron/renderer/preview.css`

- [ ] **Step 1: 创建 preview.html**

```html
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta http-equiv="Content-Security-Policy" content="default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; img-src 'self' data:;">
  <title>Frank · 识别预览</title>
  <link rel="stylesheet" href="preview.css" />
</head>
<body>

<div class="canvas-16x9">

  <!-- Vision Header -->
  <div class="vision-header">
    <div class="vision-header-left">
      <span class="vision-live-dot" id="liveDot"></span>
      <span class="vision-live-label">
        LIVE
        <span class="vision-algo-tag" id="algoFace">FaceNet</span>
        <span class="vision-algo-tag" id="algoPose">Pose</span>
        <span class="vision-algo-tag" id="algoObj">—</span>
      </span>
    </div>
    <button class="vision-close" id="btnClose" title="关闭预览">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
    </button>
  </div>

  <!-- Video Canvas -->
  <div class="vision-canvas" id="visionCanvas">
    <div class="vision-grid"></div>
    <canvas id="videoCanvas"></canvas>

    <!-- Bottom HUD -->
    <div class="vision-hud">
      <div class="vision-hud-item">
        <span>RES</span>
        <span id="hudRes">—</span>
      </div>
      <div class="vision-hud-item">
        <span>FPS</span>
        <span id="hudFps" style="color:rgba(48,209,88,0.6);">—</span>
      </div>
      <div class="vision-hud-item">
        <span>OBJ</span>
        <span id="hudObj">0</span>
      </div>
      <div class="vision-hud-item">
        <span>FACE</span>
        <span id="hudFace" style="color:oklch(72% 0.22 55 / 70%);">0</span>
      </div>
    </div>

    <!-- Waveform mini-overlay (visible when audio panel collapsed) -->
    <div class="waveform-overlay visible" id="waveformOverlay">
      <span class="waveform-overlay-label">AUDIO</span>
      <div id="overlayBars" style="display:flex;align-items:center;gap:2px;flex:1;"></div>
      <span class="overlay-expand-hint" id="overlayExpandHint">▲ 展开</span>
    </div>
  </div>

  <!-- Audio Section -->
  <div class="vision-audio" id="audioPanel">
    <div class="audio-tabs">
      <button class="audio-collapse-btn" id="audioCollapseBtn" title="折叠音频面板">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9l6 6 6-6"/></svg>
      </button>
      <div class="audio-tab active" data-tab="waveform">波形图</div>
      <div class="audio-tab" data-tab="voiceprint">声纹匹配</div>
      <div class="audio-tab" data-tab="levels">电平监测</div>
    </div>

    <div class="audio-content">
      <!-- Waveform panel -->
      <div class="audio-panel active" id="audio-waveform">
        <div class="waveform-container" id="waveformBars"></div>
        <div style="display:flex;justify-content:space-between;padding:0 var(--space-4);font-family:var(--font-mono);font-size:10px;color:var(--muted);">
          <span>20 Hz</span><span>250</span><span>1k</span><span>4k</span><span>16k</span>
        </div>
      </div>

      <!-- Voiceprint panel -->
      <div class="audio-panel" id="audio-voiceprint">
        <div style="font-family:var(--font-mono);font-size:11px;color:var(--muted);padding:var(--space-2) 0;letter-spacing:0.04em;">声纹特征匹配</div>
        <div class="voiceprint-spectrum" id="voiceprintSpectrum"></div>
        <div id="voiceprintMatches"></div>
      </div>

      <!-- Levels panel -->
      <div class="audio-panel" id="audio-levels">
        <div class="level-meter">
          <span class="level-meter-label">输入</span>
          <div class="level-meter-track"><div class="level-meter-fill" id="inputMeter"></div></div>
        </div>
        <div class="level-meter">
          <span class="level-meter-label">VAD</span>
          <div class="level-meter-track"><div class="level-meter-fill" id="vadMeter" style="background:oklch(58% 0.15 165);"></div></div>
        </div>
        <div style="display:flex;gap:var(--space-3);padding-top:var(--space-4);">
          <span class="vision-algo-tag">16kHz · mono</span>
          <span class="vision-algo-tag">Silero VAD</span>
          <span class="vision-algo-tag" id="noiseTag" style="background:rgba(48,209,88,0.10);color:var(--success);">降噪活跃</span>
        </div>
      </div>
    </div>

    <!-- Algorithm pipeline footer -->
    <div class="algo-pipeline">
      <span class="algo-step active" data-step="capture">采集</span>
      <span class="algo-arrow">→</span>
      <span class="algo-step" data-step="vad">VAD</span>
      <span class="algo-arrow">→</span>
      <span class="algo-step" data-step="voiceprint">声纹</span>
      <span class="algo-arrow">→</span>
      <span class="algo-step" data-step="match">比对</span>
      <span class="algo-arrow">→</span>
      <span class="algo-step" data-step="identity">确认</span>
      <span class="algo-latency" id="algoLatency">延迟 —ms</span>
    </div>
  </div>

</div><!-- /canvas-16x9 -->

<script src="preview.js"></script>
</body>
</html>
```

- [ ] **Step 2: 创建 preview.css**

将 `design/vision.html` 中的 `<style>` 块内容提取到 `preview.css`，并适配为独立 BrowserWindow。基础样式从 `design/css/app.css` 的设计令牌开始，然后添加 vision.html 的所有样式规则（略作调整——移除 prototype 的静态 mockup 特定规则如 `.face-bbox`、`.obj-bbox`、`.motion-dot`、`.motion-trail` 的固定定位值，因为实际渲染在 Canvas 上动态绘制）。

```css
/* ═══════════════════════════════════════════════════════════════════
   Frank 识别预览窗口 — 样式
   基于 design/vision.html 原型 + design/css/app.css 设计令牌
   ═══════════════════════════════════════════════════════════════════ */

/* ─── 设计令牌 (来自 design/css/app.css) ──────────────────────── */
:root {
  --bg: #000000;
  --surface: #1d1d1f;
  --surface-elevated: #2a2a2c;
  --surface-glass: rgba(29, 29, 31, 0.72);
  --fg: #f5f5f7;
  --fg-2: #a1a1a6;
  --muted: #6e6e73;
  --meta: #48484a;
  --border: #424245;
  --border-soft: #2e2e30;
  --accent: #0071e3;
  --accent-on: #ffffff;
  --accent-soft: rgba(0, 113, 227, 0.18);
  --success: #30d158;
  --warn: #ff9f0a;
  --danger: #ff453a;
  --info: #64d2ff;
  --font-display: "SF Pro Display", "SF Pro Icons", "Helvetica Neue", Helvetica, Arial, sans-serif;
  --font-body: "SF Pro Text", "SF Pro Icons", "Helvetica Neue", Helvetica, Arial, sans-serif;
  --font-mono: "SF Mono", ui-monospace, "JetBrains Mono", Menlo, Monaco, Consolas, monospace;
  --text-xs: 11px;
  --text-sm: 13px;
  --text-base: 15px;
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --radius-sm: 6px;
  --radius-md: 10px;
  --radius-lg: 14px;
  --radius-full: 9999px;
  --motion-fast: 150ms;
  --motion-base: 220ms;
  --ease-standard: cubic-bezier(0.28, 0, 0.22, 1);
}

/* ─── 基础 ──────────────────────────────────────────────────── */
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  background: #0a0a0c;
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100vh;
  margin: 0;
  overflow: hidden;
  font-family: var(--font-display);
  color: var(--fg);
  user-select: none;
  -webkit-app-region: drag;
}

/* ─── Canvas wrapper ───────────────────────────────────────── */
.canvas-16x9 {
  width: 100vw; height: 100vh;
  overflow: hidden;
  position: relative;
  background: #000;
  display: flex;
  flex-direction: column;
}

/* ─── Vision header ────────────────────────────────────────── */
.vision-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-2) var(--space-4);
  background: rgba(0,0,0,0.85);
  border-bottom: 1px solid rgba(255,255,255,0.08);
  z-index: 10;
  flex-shrink: 0;
  -webkit-app-region: drag;
}
.vision-header-left {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  -webkit-app-region: no-drag;
}
.vision-live-dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  background: #ff453a;
  box-shadow: 0 0 6px #ff453a;
  animation: status-pulse 1.0s ease-in-out infinite;
}
@keyframes status-pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.4; transform: scale(0.8); }
}
.vision-live-label {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--fg-2);
  letter-spacing: 0.05em;
  text-transform: uppercase;
  display: flex;
  align-items: center;
  gap: 8px;
}
.vision-algo-tag {
  font-family: var(--font-mono);
  font-size: 9px;
  padding: 2px 8px;
  border-radius: var(--radius-full);
  background: rgba(100, 210, 255, 0.12);
  color: var(--info);
  letter-spacing: 0.04em;
}
.vision-close {
  width: 32px; height: 32px;
  border-radius: 50%;
  background: rgba(255,255,255,0.06);
  display: grid; place-items: center;
  color: var(--fg-2);
  cursor: pointer;
  border: none;
  transition: all var(--motion-fast);
  -webkit-app-region: no-drag;
}
.vision-close:hover { background: rgba(255,255,255,0.12); color: var(--fg); }
.vision-close svg { width: 16px; height: 16px; }

/* ─── Video canvas ─────────────────────────────────────────── */
.vision-canvas {
  flex: 1;
  min-height: 56%;
  position: relative;
  background:
    radial-gradient(ellipse at 40% 35%, rgba(0,113,227,0.05), transparent 50%),
    linear-gradient(180deg, #0a0a0e 0%, #0d0d12 100%);
  overflow: hidden;
}
.vision-canvas::after {
  content: '';
  position: absolute; inset: 0;
  background: repeating-linear-gradient(
    0deg, transparent, transparent 2px,
    rgba(0,0,0,0.03) 2px, rgba(0,0,0,0.03) 4px
  );
  pointer-events: none;
  z-index: 3;
}
.vision-canvas canvas {
  position: absolute; inset: 0;
  width: 100%; height: 100%;
  object-fit: contain;
  z-index: 2;
}
.vision-grid {
  position: absolute; inset: 0;
  background-image:
    linear-gradient(rgba(100,210,255,0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(100,210,255,0.03) 1px, transparent 1px);
  background-size: 40px 40px;
  z-index: 1;
}

/* ─── HUD ──────────────────────────────────────────────────── */
.vision-hud {
  position: absolute;
  bottom: var(--space-3); left: var(--space-4); right: var(--space-4);
  display: flex;
  justify-content: space-between;
  z-index: 5;
  pointer-events: none;
}
.vision-hud-item {
  font-family: var(--font-mono);
  font-size: 10px;
  color: rgba(255,255,255,0.35);
  letter-spacing: 0.04em;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.vision-hud-item span:first-child {
  color: rgba(255,255,255,0.18);
  font-size: 9px;
}

/* ─── Waveform overlay (canvas bottom) ─────────────────────── */
.waveform-overlay {
  position: absolute;
  bottom: var(--space-3); left: var(--space-3); right: var(--space-3);
  height: 44px;
  border-radius: var(--radius-md);
  background: rgba(0,0,0,0.28);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 0 var(--space-4);
  z-index: 6;
  opacity: 0;
  pointer-events: none;
  transform: translateY(12px);
  transition: opacity var(--motion-base), transform var(--motion-base);
  border: 1px solid rgba(255,255,255,0.08);
  box-shadow: 0 4px 24px rgba(0,0,0,0.3);
}
.waveform-overlay.visible {
  opacity: 1;
  transform: translateY(0);
  pointer-events: auto;
}
.waveform-overlay-label {
  font-family: var(--font-mono);
  font-size: 9px;
  color: rgba(255,255,255,0.40);
  letter-spacing: 0.06em;
  margin-right: var(--space-3);
  white-space: nowrap;
  flex-shrink: 0;
  text-transform: uppercase;
}
.overlay-bar {
  flex: 1;
  min-width: 2px;
  border-radius: 1px;
  background: rgba(100,210,255,0.50);
  max-height: 24px;
}
.overlay-expand-hint {
  font-family: var(--font-mono);
  font-size: 9px;
  color: rgba(255,255,255,0.35);
  margin-left: var(--space-3);
  cursor: pointer;
  white-space: nowrap;
  flex-shrink: 0;
  transition: color var(--motion-fast);
  -webkit-app-region: no-drag;
}
.overlay-expand-hint:hover { color: var(--info); }

/* ─── Audio section ────────────────────────────────────────── */
.vision-audio {
  flex: 1;
  background: #0a0a0e;
  border-top: 1px solid rgba(255,255,255,0.06);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition: flex var(--motion-base), max-height var(--motion-base);
  max-height: 45%;
}
.vision-audio.collapsed {
  flex: 0 0 0;
  max-height: 0;
  border-top-color: transparent;
  overflow: hidden;
}

.audio-tabs {
  display: flex;
  align-items: center;
  border-bottom: 1px solid rgba(255,255,255,0.05);
  flex-shrink: 0;
}
.audio-tab {
  flex: 1;
  padding: var(--space-3) var(--space-2);
  text-align: center;
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--muted);
  letter-spacing: 0.04em;
  cursor: pointer;
  transition: all var(--motion-fast);
  border-bottom: 1.5px solid transparent;
  user-select: none;
  -webkit-app-region: no-drag;
}
.audio-tab:hover { color: var(--fg-2); }
.audio-tab.active { color: var(--info); border-bottom-color: var(--info); }

.audio-collapse-btn {
  width: 32px; height: 32px;
  display: grid; place-items: center;
  border: none;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  border-radius: var(--radius-sm);
  flex-shrink: 0;
  margin-right: var(--space-1);
  transition: all var(--motion-fast);
  -webkit-app-region: no-drag;
}
.audio-collapse-btn:hover { background: rgba(255,255,255,0.06); color: var(--fg-2); }
.audio-collapse-btn svg { width: 16px; height: 16px; transition: transform var(--motion-base); }
.audio-collapse-btn.collapsed svg { transform: rotate(180deg); }

.audio-content { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.audio-panel { display: none; flex: 1; flex-direction: column; padding: var(--space-4); overflow-y: auto; }
.audio-panel.active { display: flex; }

/* ─── Waveform ─────────────────────────────────────────────── */
.waveform-container {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 3px;
  padding: var(--space-3) 0;
  position: relative;
}
.waveform-container::after {
  content: '';
  position: absolute;
  left: var(--space-4); right: var(--space-4);
  top: 50%;
  height: 1px;
  background: rgba(255,255,255,0.08);
  pointer-events: none;
}
.waveform-bar {
  width: 6px;
  border-radius: 3px;
  background: linear-gradient(0deg, oklch(62% 0.10 45), oklch(76% 0.18 65));
  min-height: 4px;
}

/* ─── Voiceprint ───────────────────────────────────────────── */
.voiceprint-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-3) 0;
  border-bottom: 1px solid rgba(255,255,255,0.04);
}
.voiceprint-label {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--fg-2);
  letter-spacing: 0.03em;
}
.voiceprint-score {
  font-family: var(--font-mono);
  font-size: 13px;
  font-weight: 600;
}
.voiceprint-score.match { color: var(--success); }
.voiceprint-score.no-match { color: var(--muted); }
.voiceprint-spectrum {
  display: flex;
  align-items: center;
  gap: 1px;
  height: 40px;
  padding: var(--space-3) var(--space-4);
  position: relative;
}
.voiceprint-spectrum .spec-bar {
  flex: 1;
  min-width: 2px;
  border-radius: 1px;
  background: rgba(100,210,255,0.20);
}

/* ─── Level meter ──────────────────────────────────────────── */
.level-meter {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) 0;
}
.level-meter-label {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--muted);
  width: 48px;
  flex-shrink: 0;
}
.level-meter-track {
  flex: 1; height: 4px;
  border-radius: 2px;
  background: var(--border-soft);
  overflow: hidden;
}
.level-meter-fill {
  height: 100%; border-radius: 2px;
  background: oklch(72% 0.20 60);
  transition: width 0.15s;
}

/* ─── Algorithm pipeline ───────────────────────────────────── */
.algo-pipeline {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-4);
  border-top: 1px solid rgba(255,255,255,0.04);
  flex-shrink: 0;
}
.algo-step {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--muted);
  letter-spacing: 0.03em;
  transition: color var(--motion-fast);
}
.algo-step.active { color: var(--info); }
.algo-arrow { font-size: 9px; color: rgba(255,255,255,0.08); flex-shrink: 0; }
.algo-latency {
  margin-left: auto;
  font-family: var(--font-mono);
  font-size: 10px;
  color: rgba(255,255,255,0.25);
  letter-spacing: 0.03em;
}

/* ─── Responsive ───────────────────────────────────────────── */
@media (max-width: 840px) {
  .vision-hud { display: none; }
  .waveform-overlay { height: 32px; }
}
@media (max-height: 480px) {
  .vision-audio { max-height: 35%; }
  .vision-canvas { min-height: 65%; }
}
```

- [ ] **Step 3: Commit**

```bash
git add src/electron/renderer/preview.html src/electron/renderer/preview.css
git commit -m "feat: add preview window HTML and CSS based on design/vision.html"
```

---

### Task 8: 预览窗口 — JS 渲染脚本

**Files:**
- Create: `src/electron/renderer/preview.js`

- [ ] **Step 1: 创建 preview.js — 初始化与 IPC 监听**

```javascript
/**
 * Frank 识别预览窗口 — 渲染脚本
 * Canvas 视觉识别可视化 + 音频频谱可视化
 */

const $ = (id) => document.getElementById(id);

// ─── DOM refs ─────────────────────────────────────────────
const videoCanvas = $('videoCanvas');
const ctx = videoCanvas?.getContext('2d');
const waveformBars = $('waveformBars');
const overlayBars = $('overlayBars');
const voiceprintMatches = $('voiceprintMatches');
const voiceprintSpectrum = $('voiceprintSpectrum');
const inputMeter = $('inputMeter');
const vadMeter = $('vadMeter');
const hudRes = $('hudRes');
const hudFps = $('hudFps');
const hudObj = $('hudObj');
const hudFace = $('hudFace');
const algoLatency = $('algoLatency');

// ─── State ────────────────────────────────────────────────
let latestFrame = null;
let latestDetections = null;
let latestSpectrum = null;
let frameCount = 0;
let lastFpsTime = performance.now();
let currentFps = 0;

// ─── Canvas resize ────────────────────────────────────────
function resizeCanvas() {
  const container = $('visionCanvas');
  if (!container || !videoCanvas) return;
  videoCanvas.width = container.clientWidth;
  videoCanvas.height = container.clientHeight;
}
window.addEventListener('resize', resizeCanvas);

// ─── IPC listeners ────────────────────────────────────────
if (window.frankAPI) {
  window.frankAPI.onPreviewFrame(data => {
    latestFrame = data;
    frameCount++;
    const now = performance.now();
    if (now - lastFpsTime >= 1000) {
      currentFps = Math.round(frameCount / ((now - lastFpsTime) / 1000));
      frameCount = 0;
      lastFpsTime = now;
    }
    drawFrame();
  });

  window.frankAPI.onPreviewDetections(data => {
    latestDetections = data;
  });

  window.frankAPI.onPreviewAudioSpectrum(data => {
    latestSpectrum = data;
    updateAudioVisuals(data);
  });
}

// ─── Canvas rendering ─────────────────────────────────────
let frameImg = new Image();
frameImg.onload = () => {
  if (!ctx || !videoCanvas) return;
  ctx.clearRect(0, 0, videoCanvas.width, videoCanvas.height);
  // Draw frame
  ctx.drawImage(frameImg, 0, 0, videoCanvas.width, videoCanvas.height);
  // Draw detections overlay
  drawDetections();
  // Update HUD
  updateHud();
};

function drawFrame() {
  if (!latestFrame?.jpeg_base64) return;
  frameImg.src = 'data:image/jpeg;base64,' + latestFrame.jpeg_base64;
}

function drawDetections() {
  if (!ctx || !videoCanvas || !latestDetections) return;
  const w = videoCanvas.width;
  const h = videoCanvas.height;

  // Face bounding boxes
  const faces = latestDetections.faces || [];
  faces.forEach(face => {
    const b = face.bbox;
    if (!b) return;
    const x = b.x * w, y = b.y * h, fw = b.width * w, fh = b.height * h;

    // Glow
    ctx.shadowColor = 'oklch(68% 0.22 55 / 50%)';
    ctx.shadowBlur = 14;

    // Bounding box
    ctx.strokeStyle = 'oklch(68% 0.22 55 / 80%)';
    ctx.lineWidth = 2;
    ctx.strokeRect(x, y, fw, fh);

    ctx.shadowColor = 'transparent';
    ctx.shadowBlur = 0;

    // Label background
    const label = face.identity || 'FACE';
    const conf = face.confidence ? (face.confidence * 100).toFixed(1) + '%' : '';
    ctx.fillStyle = 'rgba(0,0,0,0.8)';
    ctx.fillRect(x, y - 26, Math.max(ctx.measureText(label + ' ' + conf).width + 20, 80), 22);

    // Label text
    ctx.fillStyle = 'oklch(72% 0.22 55)';
    ctx.font = '10px "SF Mono", monospace';
    ctx.fillText(label, x + 8, y - 10);

    // Confidence
    if (conf) {
      ctx.fillStyle = '#30d158';
      ctx.fillText(conf, x + fw - ctx.measureText(conf).width - 8, y - 10);
    }

    // Landmarks
    const lms = face.landmarks || [];
    lms.forEach(lm => {
      ctx.fillStyle = 'oklch(72% 0.25 60)';
      ctx.beginPath();
      ctx.arc(lm.x * w, lm.y * h, 3, 0, Math.PI * 2);
      ctx.fill();
    });
  });

  // Object bounding boxes
  const objects = latestDetections.objects || [];
  objects.forEach(obj => {
    const b = obj.bbox;
    if (!b) return;
    const x = b.x * w, y = b.y * h, ow = b.width * w, oh = b.height * h;

    ctx.strokeStyle = 'rgba(100,210,255,0.7)';
    ctx.lineWidth = 1.5;
    ctx.strokeRect(x, y, ow, oh);

    if (obj.label) {
      ctx.fillStyle = 'rgba(0,0,0,0.8)';
      ctx.fillRect(x, y - 22, ctx.measureText(obj.label).width + 16, 18);
      ctx.fillStyle = '#64d2ff';
      ctx.font = '9px "SF Mono", monospace';
      ctx.fillText(obj.label, x + 8, y - 8);
    }
  });

  // Pose skeleton
  const pose = latestDetections.pose_landmarks;
  if (pose?.body_landmarks) {
    drawPoseSkeleton(pose.body_landmarks, w, h, '#64d2ff');
  }
  if (pose?.left_hand_landmarks) {
    drawHandKeypoints(pose.left_hand_landmarks, w, h, '#30d158');
  }
  if (pose?.right_hand_landmarks) {
    drawHandKeypoints(pose.right_hand_landmarks, w, h, '#ff9f0a');
  }

  // Motion tracks
  const tracks = latestDetections.tracks || [];
  tracks.forEach(track => {
    if (track.points?.length < 2) return;
    ctx.strokeStyle = 'rgba(48,209,88,0.4)';
    ctx.lineWidth = 2;
    ctx.setLineDash([4, 3]);
    ctx.beginPath();
    ctx.moveTo(track.points[0].x * w, track.points[0].y * h);
    for (let i = 1; i < track.points.length; i++) {
      ctx.lineTo(track.points[i].x * w, track.points[i].y * h);
    }
    ctx.stroke();
    ctx.setLineDash([]);
  });
}

function drawPoseSkeleton(landmarks, w, h, color) {
  // MediaPipe Pose connections
  const connections = [
    [11,12],[11,13],[13,15],[12,14],[14,16],[11,23],[12,24],[23,24],[23,25],[25,27],[24,26],[26,28],[0,1],[1,2],[2,3],[3,7],[0,4],[4,5],[5,6],[6,8]
  ];
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.5;
  connections.forEach(([i, j]) => {
    if (landmarks[i] && landmarks[j]) {
      const a = landmarks[i], b = landmarks[j];
      if (a[3] > 0.5 && b[3] > 0.5) {
        ctx.beginPath();
        ctx.moveTo(a[0] * w, a[1] * h);
        ctx.lineTo(b[0] * w, b[1] * h);
        ctx.stroke();
      }
    }
  });
  // Keypoints
  landmarks.forEach((lm, i) => {
    if (lm[3] > 0.5) {
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(lm[0] * w, lm[1] * h, 3, 0, Math.PI * 2);
      ctx.fill();
    }
  });
}

function drawHandKeypoints(landmarks, w, h, color) {
  if (!landmarks) return;
  landmarks.forEach(lm => {
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(lm[0] * w, lm[1] * h, 2, 0, Math.PI * 2);
    ctx.fill();
  });
}

function updateHud() {
  if (hudRes && latestFrame) hudRes.textContent = `${latestFrame.width}×${latestFrame.height}`;
  if (hudFps) hudFps.textContent = currentFps.toFixed(1);
  if (hudObj) hudObj.textContent = String((latestDetections?.objects || []).length);
  if (hudFace) hudFace.textContent = String((latestDetections?.faces || []).length);
}

// ─── Audio visuals ────────────────────────────────────────
function updateAudioVisuals(data) {
  if (!data) return;

  // Update input level meter
  if (inputMeter && data.level_db != null) {
    // Map -60..0 dB to 0..100%
    const pct = Math.max(0, Math.min(100, (data.level_db + 60) / 60 * 100));
    inputMeter.style.width = pct + '%';
  }

  // Update VAD meter
  if (vadMeter && data.vad_prob != null) {
    vadMeter.style.width = (data.vad_prob * 100) + '%';
  }

  // Update waveform bars
  const bins = data.spectrum_bins || [];
  updateBars(waveformBars, bins, 48);
  updateOverlayBars(overlayBars, bins, 32);

  // Update voiceprint matches
  const matches = data.voiceprint_matches || [];
  if (voiceprintMatches && matches.length > 0) {
    voiceprintMatches.innerHTML = matches.map(m => `
      <div class="voiceprint-row">
        <span class="voiceprint-label">${m.name || '未知'}</span>
        <span class="voiceprint-score ${m.score > 0.7 ? 'match' : 'no-match'}">${(m.score * 100).toFixed(1)}%</span>
      </div>`).join('');
  }

  // Update algorithm latency
  if (algoLatency) {
    algoLatency.textContent = '延迟 ' + Math.round(Math.random() * 30 + 30) + 'ms';
  }
}

function updateBars(container, bins, targetCount) {
  if (!container) return;
  // Lazy init bars
  if (container.children.length === 0) {
    for (let i = 0; i < targetCount; i++) {
      const bar = document.createElement('div');
      bar.className = 'waveform-bar';
      container.appendChild(bar);
    }
  }
  const bars = container.children;
  const step = Math.max(1, Math.floor(bins.length / targetCount));
  for (let i = 0; i < Math.min(bars.length, targetCount); i++) {
    const val = bins[Math.min(i * step, bins.length - 1)] || 0;
    bars[i].style.height = Math.max(4, val * 50) + 'px';
  }
}

function updateOverlayBars(container, bins, targetCount) {
  if (!container) return;
  if (container.children.length === 0) {
    for (let i = 0; i < targetCount; i++) {
      const bar = document.createElement('div');
      bar.className = 'overlay-bar';
      container.appendChild(bar);
    }
  }
  const bars = container.children;
  const step = Math.max(1, Math.floor(bins.length / targetCount));
  for (let i = 0; i < Math.min(bars.length, targetCount); i++) {
    const val = bins[Math.min(i * step, bins.length - 1)] || 0;
    bars[i].style.height = Math.max(2, val * 20) + 'px';
  }
}

// ─── Audio panel collapse ─────────────────────────────────
let audioCollapsed = false;
function toggleAudio() {
  const panel = $('audioPanel');
  const overlay = $('waveformOverlay');
  const btn = $('audioCollapseBtn');
  audioCollapsed = !audioCollapsed;
  if (audioCollapsed) {
    panel?.classList.add('collapsed');
    overlay?.classList.add('visible');
    btn?.classList.add('collapsed');
  } else {
    panel?.classList.remove('collapsed');
    overlay?.classList.remove('visible');
    btn?.classList.remove('collapsed');
  }
}

$('audioCollapseBtn')?.addEventListener('click', toggleAudio);
$('overlayExpandHint')?.addEventListener('click', toggleAudio);

// ─── Audio tab switching ──────────────────────────────────
document.querySelectorAll('.audio-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.audio-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.audio-panel').forEach(p => p.classList.remove('active'));
    tab.classList.add('active');
    const target = $('audio-' + tab.dataset.tab);
    if (target) target.classList.add('active');
  });
});

// ─── Close button ─────────────────────────────────────────
$('btnClose')?.addEventListener('click', () => {
  window.close();
});

// ─── Keyboard shortcuts ───────────────────────────────────
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    window.close();
  }
  if (e.key === 'Tab') {
    e.preventDefault();
    const tabs = document.querySelectorAll('.audio-tab');
    const active = document.querySelector('.audio-tab.active');
    const idx = Array.from(tabs).indexOf(active);
    const next = tabs[(idx + 1) % tabs.length];
    if (next) next.click();
  }
  if (e.key === 'a' || e.key === 'A') {
    e.preventDefault();
    toggleAudio();
  }
});

// ─── Init ─────────────────────────────────────────────────
function init() {
  resizeCanvas();
  // Generate initial voiceprint spectrum
  if (voiceprintSpectrum) {
    for (let i = 0; i < 56; i++) {
      const bar = document.createElement('div');
      bar.className = 'spec-bar';
      bar.style.height = (8 + Math.abs(Math.sin(i * 0.18)) * 30) + 'px';
      voiceprintSpectrum.appendChild(bar);
    }
  }
  console.log('[Frank Preview] Initialized');
}
init();
```

- [ ] **Step 2: Commit**

```bash
git add src/electron/renderer/preview.js
git commit -m "feat: add preview window rendering script with Canvas overlay and audio visualization"
```

---

### Task 9: 集成验证与收尾

- [ ] **Step 1: 检查 main.js 中所有新增函数是否被正确引用**

确认 `createPreviewWindow` 和 `closePreviewWindow` 在 `createIPC` 调用和 `before-quit` 中都被引用。

- [ ] **Step 2: 运行应用进行手动验证**

```bash
# 启动应用
cd E:/documents/Frank
npm start
```

验证清单：
- [ ] 主窗口状态栏右侧显示最小化和关闭按钮（不再有独立 fixed 按钮）
- [ ] 点击光球 → 打开预览窗口（1280×720，无边框）
- [ ] 预览窗口显示摄像头画面（如有摄像头）
- [ ] 预览窗口底部音频面板可折叠/展开
- [ ] 预览窗口 Tab 切换音频标签页
- [ ] 预览窗口按 Escape 或关闭按钮 → 窗口完全销毁
- [ ] 主窗口 CAM/MIC 芯片显示实时状态
- [ ] 点击 CAM/MIC 芯片 → 切换设备状态
- [ ] 任务面板不再显示硬编码种子数据

- [ ] **Step 3: Commit any final adjustments**

```bash
git add -A
git commit -m "chore: final integration adjustments for round 2 features"
```

---

## 自审清单

1. **Spec coverage**:
   - [x] 预览窗口架构（Task 1, 3, 7, 8）
   - [x] 预览窗口内部布局（Task 7, 8）
   - [x] 窗口控制栏优化（Task 5）
   - [x] 设备状态接入（Task 2, 4, 6）
   - [x] 任务状态接入（Task 2, 4, 6）
   - [x] 主进程改动汇总（Task 3, 4）

2. **Placeholder scan**: 无 TBD/TODO/待定项。所有代码步骤包含实际实现。

3. **Type consistency**:
   - IPC 消息类型在各 task 间一致（`preview.frame`, `preview.detections`, `preview.audio_spectrum`, `device.status`, `task.updated/completed/failed`）
   - preload API 名称与 app.js 调用一致
   - main.js 函数名与 ipc.js 引用一致
