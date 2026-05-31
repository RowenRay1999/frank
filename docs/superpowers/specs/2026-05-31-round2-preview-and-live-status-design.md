# Frank 第二轮需求 — 识别预览窗口 + 实时状态接入 设计文档

> 日期：2026-05-31 | 分支：`develop-base-v0` | 状态：设计完成

## 需求概述

1. **识别效果预览窗口**：点击智能体状态动效区域（Frank Orb 光球）打开独立窗口，展示视觉识别可视化（目标识别、人脸识别、动作跟踪）和音频频谱可视化
2. **窗口控制栏优化**：将关闭/最小化按钮移入顶部状态栏内部，不与界面重叠
3. **设备实际状态接入**：CAM / MIC / SCR 芯片接入实时设备状态，支持悬浮指标和点击快速操作
4. **活动/任务执行状态接入**：执行状态面板区和对话区接入后端实时事件，替换硬编码种子数据

---

## 一、预览窗口架构（独立 BrowserWindow）

### 1.1 窗口模型

预览窗口作为独立的第二个 `BrowserWindow`，与主窗口平级：

- **创建时机**：主窗口点击 Frank Orb 光球时，通过 IPC `frank:openPreview` 触发主进程创建。光球原有的"打开对话覆盖层"行为移除
- **对话入口替代**：光球下方的 agent label 文本（"聆听中 · 等待唤醒"）改为可点击，点击打开 Chat Overlay；同时保留空格键快捷方式和 convo-bar 展开按钮作为对话入口
- **销毁时机**：预览窗口点击关闭按钮 / 按 Escape → `window.destroy()` 完全销毁（释放所有渲染和视频资源）
- **主窗口退出时**：若预览窗口存在，一并销毁
- **窗口属性**：
  - 尺寸：1280×720（16:9），可缩放
  - `frame: false`（无边框，与主窗口一致）
  - `backgroundColor: '#0a0a0c'`
  - 加载独立的 `src/electron/renderer/preview.html`

### 1.2 数据通道

```
CameraPipeline ─┐
                ├─→ WebSocket ─→ main.js ─┬─→ 主窗口 (状态事件)
AudioPipeline  ─┘                         └─→ 预览窗口 (帧+元数据)
```

- Python 后端 → WebSocket → Electron 主进程 → IPC → 预览窗口
- 主进程作为数据路由中心，根据消息类型决定转发到哪个窗口

### 1.3 帧推送协议（混合模式）

| 消息类型 | 方向 | 频率 | Payload |
|---------|------|------|---------|
| `preview.frame` | 后端→主进程→预览窗口 | ~10fps | `{frame_id, jpeg_base64, width, height, timestamp}` |
| `preview.detections` | 后端→主进程→预览窗口 | ~10fps | `{frame_id, faces[], objects[], pose_landmarks, gesture, fps}` |
| `preview.audio_spectrum` | 后端→主进程→预览窗口 | ~20fps | `{spectrum_bins[32], vad_prob, level_db, wake_word_trigger, pitch_hz, voiceprint_matches[]}` |
| `preview.open` | 主进程→后端 (WebSocket) | 事件 | `{type: "preview.open"}` — 后端开始推送帧 |
| `preview.close` | 主进程→后端 (WebSocket) | 事件 | `{type: "preview.close"}` — 后端停止推送帧 |

- `preview.frame`：JPEG 编码的原始帧（~30-50KB/帧 @ 640×480），前端 `<canvas>` 解码绘制
- `preview.detections`：结构化识别结果（人脸 bbox + 身份标记、目标检测框 + 标签/置信度、姿态 33 关键点 + 双手 21 关键点、当前手势类型/置信度）
- `preview.audio_spectrum`：FFT 频谱分箱值 + VAD 概率 + 唤醒词触发标记 + 基频追踪 + 声纹匹配分数列表

### 1.4 后端改动

在 `camera_pipeline.py` 和 `audio_pipeline.py` 中新增预览数据推送：

- **CameraPipeline**：在 `_capture_loop()` 中，当 `_preview_active` 标记为 True 时：
  - 将当前帧 JPEG 编码为 base64，发送 `preview.frame`
  - 将检测结果（人脸/姿态/手势）打包为 `preview.detections`
- **AudioPipeline**：在 `_process_loop()` 中，当 `_preview_active` 标记为 True 时：
  - 计算 FFT 频谱（32-bin），发送 `preview.audio_spectrum`
  - 附带 VAD 概率、当前音量电平、唤醒词触发标记、基频估计
- 后端通过 `server/main.py` 中新增的 WebSocket 消息处理来开关 `_preview_active` 标记

### 1.5 主进程改动

`main.js` 新增：

```javascript
// 预览窗口管理
let previewWindow = null;

function createPreviewWindow() {
  if (previewWindow && !previewWindow.isDestroyed()) {
    previewWindow.focus();
    return;
  }
  previewWindow = new BrowserWindow({
    width: 1280, height: 720,
    minWidth: 800, minHeight: 450,
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
  // 通知后端开始推送预览数据
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

消息路由新增：
- `preview.frame` / `preview.detections` / `preview.audio_spectrum` → 转发到 `previewWindow`
- IPC handler: `frank:openPreview` / `frank:closePreview`

### 1.6 Preload 新增 API

```javascript
openPreview: () => ipcRenderer.invoke('frank:openPreview'),
closePreview: () => ipcRenderer.invoke('frank:closePreview'),
onPreviewFrame: (cb) => { /* preview.frame listener */ },
onPreviewDetections: (cb) => { /* preview.detections listener */ },
onPreviewAudioSpectrum: (cb) => { /* preview.audio_spectrum listener */ },
```

---

## 二、预览窗口内部布局

以 `design/vision.html` 原型为准，整体结构：

```
┌─ preview.html ──────────────────────────────────────┐
│ .canvas-16x9 (16:9 wrapper, 1280×720)              │
│ ┌─ .vision-header ────────────────────────────────┐ │
│ │ ● LIVE  [YOLO-nano] [FaceNet] [DeepSORT]    [✕] │ │
│ └─────────────────────────────────────────────────┘ │
│ ┌─ .vision-canvas (flex: 1, min-height: 56%) ────┐ │
│ │   .vision-grid (网格叠加)                       │ │
│ │   <canvas id="videoCanvas"> (主渲染区)          │ │
│ │     — 原始帧 JPEG 背景                          │ │
│ │     — 人脸边界框 + 关键点 + 身份标签 + 置信度    │ │
│ │     — 目标检测边界框 + 标签 + 置信度            │ │
│ │     — 姿态骨架连线 (33 身体 + 21×2 手部)        │ │
│ │     — 运动轨迹线 (DeepSORT track trails)        │ │
│ │   .vision-hud (底部 HUD)                        │ │
│ │     RES: 1280×720  FPS: 29.8  OBJ: 3  FACE: 1  │ │
│ │   .waveform-overlay (折叠态音频迷你叠加层)      │ │
│ └─────────────────────────────────────────────────┘ │
│ ┌─ .vision-audio (可折叠音频面板) ────────────────┐ │
│ │   [▼] [波形图] [声纹匹配] [电平监测]            │ │
│ │   ┌─ 波形图面板 ───────────────────────────┐    │ │
│ │   │  频谱柱状图 (48 bar) + 频率轴标签      │    │ │
│ │   ├─ 声纹匹配面板 ─────────────────────────┤    │ │
│ │   │  声纹频谱图 + 成员匹配分数列表         │    │ │
│ │   ├─ 电平监测面板 ─────────────────────────┤    │ │
│ │   │  输入电平 / 降噪 / VAD 指示条          │    │ │
│ │   └────────────────────────────────────────┘    │ │
│ │   .algo-pipeline: 采集→VAD→声纹→比对→确认       │ │
│ └─────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

### 2.1 Canvas 渲染管线

预览窗口使用 `<canvas>` 作为主渲染目标，每帧执行：

1. `drawImage(bitmap, 0, 0)` — 绘制 JPEG 解码后的原始帧
2. 遍历 `detections.faces[]` — 绘制人脸边界框（橙色 `oklch(68% 0.22 55)` + 发光）+ 关键点 + 身份标签（"FACE · 爸爸"）+ 置信度
3. 遍历 `detections.objects[]` — 绘制目标检测框（蓝色 `rgba(100,210,255)`）+ data-label + data-conf
4. 遍历 `detections.pose_landmarks` — 绘制姿态骨架连线（身体 33 关键点 + 手部 21×2 关键点）
5. 遍历 `detections.tracks[]` — 绘制运动轨迹线（绿色 dashed polyline）
6. 更新 HUD 读数（RES / FPS / OBJ 数 / FACE 数）

### 2.2 音频频谱可视化

- **波形图标签页**：48 个柱状条，高度绑定 `spectrum_bins[]` 实际值（低频→高频），颜色从暖色渐变到冷色，使用 `requestAnimationFrame` 驱动
- **声纹匹配标签页**：频谱迷你图 + 已注册成员声纹匹配分数列表（来自 `voiceprint_matches[]`）
- **电平监测标签页**：输入电平实时条（绑定 `level_db`）、降噪指示、VAD 指示（绑定 `vad_prob`）
- **迷你叠加层**（音频面板折叠时展开）：32 柱浮层叠加在 Canvas 底部，半透明玻璃态
- **算法管线指示器**：底部步骤条同步显示当前音频处理阶段活跃状态 + 端到端延迟

### 2.3 交互

- **关闭按钮**（.vision-close 右上角）→ `window.close()` → 主进程 `closePreviewWindow()` → 销毁窗口
- **Escape 键** → 同上
- **A 键** → 折叠/展开音频面板
- **Tab 键** → 切换音频标签页
- **窗口缩放**：响应式，Canvas 自动适应窗口大小

---

## 三、窗口控制栏优化

### 3.1 当前问题

`window-controls` 使用 `position: fixed; top: 16px; right: 16px`，与顶部状态栏在视觉上分离且可能重叠。

### 3.2 方案：融入状态栏

**HTML 改动**（`index.html`）：
- 移除独立的 `<div class="window-controls">` 块
- 在 `.status-right` 内（时钟+通知预览之后）追加两个按钮：

```html
<div class="status-right">
  <div class="time-block" id="liveTime">00:00</div>
  <div class="notif-preview hidden" id="notifPreview">...</div>
  <button class="window-ctrl-btn-mini" id="btn-minimize" title="最小化">─</button>
  <button class="window-ctrl-btn-mini close" id="btn-close" title="关闭到托盘">✕</button>
</div>
```

**CSS 改动**（`styles.css`）：
- 移除 `.window-controls` 及 `.window-ctrl-btn` 规则
- 新增 `.window-ctrl-btn-mini` 样式：紧凑尺寸（20×20），融入状态栏右侧，与时钟/通知同高
- `.status-right` 已有 `-webkit-app-region: no-drag`，按钮自动保持可点击

**JS 改动**：按钮事件绑定不变（`btn-minimize` → `minimizeWindow`，`btn-close` → `closeWindow`）

---

## 四、设备实际状态接入

### 4.1 WebSocket 消息

新增消息类型 `device.status`，后端定期推送（~1Hz）：

```json
{
  "type": "device.status",
  "payload": {
    "camera": {
      "active": true,
      "fps": 5,
      "faces_detected": 1,
      "resolution": "640x480",
      "pipeline": "InsightFace"
    },
    "microphone": {
      "active": true,
      "level_db": -24.5,
      "vad_active": false,
      "sample_rate": 16000,
      "pipeline": "Silero VAD"
    },
    "screen": {
      "active": false
    }
  }
}
```

### 4.2 芯片交互

| 芯片 | 状态显示 | 悬浮 tooltip | 点击操作 |
|------|---------|-------------|---------|
| CAM | active（橙色高亮+发光点）/<br>inactive（灰色） | "InsightFace · 5fps · 1 face" | 暂停/恢复摄像头检测<br>(发送 `camera.toggle`) |
| MIC | active / inactive | "Silero VAD · -24dB · 静音" | 静音/取消静音<br>(发送 `microphone.toggle`) |
| SCR | 始终灰色（未实现） | "屏幕录制 · 未启用" | 无操作（预留） |

### 4.3 后端改动

- 后端在 WebSocket 主循环中新增 1Hz 定时器，收集各管线状态并推送 `device.status`
- 新增 `camera.toggle` 和 `microphone.toggle` 消息处理（暂停/恢复对应管线）

### 4.4 前端改动

- 新增 `onDeviceStatus(callback)` IPC 监听器
- 更新芯片的 `.active` class 和 `title` 属性
- 芯片点击事件绑定 `toggleCamera()` / `toggleMicrophone()`

---

## 五、活动与任务执行状态接入

### 5.1 新增消息类型

| 消息类型 | Payload | 触发时机 |
|---------|---------|---------|
| `task.started` | `{task_id, title, source, timestamp}` | 任务开始执行 |
| `task.progress` | `{task_id, progress_pct, elapsed, status_text}` | 进度更新 (~2Hz) |
| `task.completed` | `{task_id, result_summary, elapsed}` | 任务完成 |
| `task.failed` | `{task_id, error, elapsed}` | 任务失败 |
| `task.list` | `{tasks: [...], active_count, total_count}` | 面板打开时全量查询 |

### 5.2 前端状态管理

```javascript
const taskHistory = [];  // 容量上限 50 条
const MAX_TASK_HISTORY = 50;

function upsertTask(task) {
  const idx = taskHistory.findIndex(t => t.task_id === task.task_id);
  if (idx >= 0) Object.assign(taskHistory[idx], task);
  else {
    taskHistory.unshift(task);
    if (taskHistory.length > MAX_TASK_HISTORY) taskHistory.pop();
  }
  renderInlineTasks(taskHistory);
}
```

- 面板打开时发送 `task.list` 请求全量列表
- 之后通过 `task.started` / `task.progress` / `task.completed` / `task.failed` 增量更新
- 已完成/失败任务保留（灰色样式），应用重启后清空

### 5.3 对话区接入

移除硬编码种子数据（`init()` 中的 `updateInlineConversation` 调用），改为监听：

- `chat.user_message` → 追加用户消息气泡，更新 topic/meta
- `chat.assistant_message` → 追加 Frank 消息气泡
- `chat.sub_state` → 更新对话状态标签（"聆听中…"/"思考中…"/"回复中…"）
- `stt.transcription` → 在对话区显示实时转写文本

### 5.4 移除种子数据

从 `app.js` 的 `init()` 中移除：
- `allTasks` 种子数组初始化
- `renderInlineTasks(allTasks)` 调用
- `updateInlineConversation(...)` 调用
- `renderNotifList(...)` 种子通知调用

改为在收到后端首批数据时渲染。

---

## 六、主进程改动汇总

### 6.1 `main.js` 新增消息路由

```javascript
// handleMessage() switch 新增：
case 'preview.frame':        // → previewWindow
case 'preview.detections':   // → previewWindow
case 'preview.audio_spectrum': // → previewWindow
case 'device.status':        // → mainWindow
case 'task.started':         // → mainWindow
case 'task.progress':        // → mainWindow
case 'task.completed':       // → mainWindow
case 'task.failed':          // → mainWindow
```

### 6.2 `main.js` 新增 IPC handler

```javascript
frank:openPreview       → createPreviewWindow()
frank:closePreview      → closePreviewWindow()
frank:toggleCamera      → sendMessage({ type: 'camera.toggle' })
frank:toggleMicrophone  → sendMessage({ type: 'microphone.toggle' })
```

### 6.3 `preload.js` 新增 API

| API | 方向 | 说明 |
|-----|------|------|
| `openPreview()` | 渲染→主 | 打开预览窗口 |
| `closePreview()` | 渲染→主 | 关闭预览窗口 |
| `toggleCamera()` | 渲染→主 | 切换摄像头 |
| `toggleMicrophone()` | 渲染→主 | 切换麦克风 |
| `onDeviceStatus(cb)` | 主→渲染 | 设备状态更新 |
| `onTaskStarted(cb)` | 主→渲染 | 任务开始 |
| `onTaskProgress(cb)` | 主→渲染 | 任务进度 |
| `onTaskCompleted(cb)` | 主→渲染 | 任务完成 |
| `onTaskFailed(cb)` | 主→渲染 | 任务失败 |
| `onPreviewFrame(cb)` | 主→渲染 | 预览帧数据 |
| `onPreviewDetections(cb)` | 主→渲染 | 预览检测结果 |
| `onPreviewAudioSpectrum(cb)` | 主→渲染 | 预览音频频谱 |

---

## 七、文件改动清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/electron/main/main.js` | 修改 | 预览窗口管理 + 消息路由 + IPC handler |
| `src/electron/main/preload.js` | 修改 | 新增预览/设备/任务 API |
| `src/electron/renderer/index.html` | 修改 | 移除独立窗口控制块，按钮移入状态栏 |
| `src/electron/renderer/styles.css` | 修改 | 新增 `.window-ctrl-btn-mini`，移除 `.window-controls` |
| `src/electron/renderer/app.js` | 修改 | 移除种子数据，新增实时事件监听，光球点击改为打开预览 |
| `src/electron/renderer/preview.html` | **新建** | 预览窗口 HTML（参考 `design/vision.html`） |
| `src/electron/renderer/preview.css` | **新建** | 预览窗口样式 |
| `src/electron/renderer/preview.js` | **新建** | 预览窗口渲染脚本（Canvas 绘制 + 音频可视化） |
| `src/python/modules/camera/camera_pipeline.py` | 修改 | 预览帧推送 (preview.frame + preview.detections) |
| `src/python/modules/audio/audio_pipeline.py` | 修改 | 预览频谱推送 (preview.audio_spectrum) |
| `src/python/server/main.py` | 修改 | device.status 定时推送 + 开关预览标记 |
| `src/python/modules/task_manager/task_manager.py` | 修改 | 任务事件推送 (task.started/progress/completed/failed) |

---

## 八、设计决策记录

| 决策 | 选项 | 理由 |
|------|------|------|
| 预览窗口架构 | 独立 BrowserWindow | 独立渲染上下文，关闭即销毁释放资源 |
| 数据推送模式 | 混合模式（JPEG帧 + 元数据JSON） | 平衡带宽和前端渲染灵活性 |
| 预览窗口生命周期 | 关闭时 destroy() | 用户要求避免后台占用性能 |
| 窗口控制栏 | 融入状态栏内部右侧 | 最大化利用空间，减少视觉干扰 |
| 设备芯片 | 状态+指标悬浮+点击操作 | 用户要求完整交互能力 |
| 任务状态 | 全事件驱动+本地缓存50条 | 实时性+重启不持久化历史 |
| 预览UI | 参考 design/vision.html | 用户指定的设计原型 |
| 光球点击行为 | 替换为打开预览窗口 | 对话入口移至导航栏/标签文本 |

---

## 九、未涵盖 / 待定

- **SCR 屏幕录制**：当前无录屏模块实现，芯片保持灰色预留态
- **目标识别 (object detection)**：当前后端仅有 MediaPipe/InsightFace 人脸检测和 MediaPipe Pose 姿态检测，YOLO 目标识别需后续集成；预览 UI 预留 `objects[]` 数据通道
- **DeepSORT 运动跟踪**：原型中展示的轨迹追踪（motion trail）当前后端未实现，预览 UI 预留 `tracks[]` 数据通道
- **预览窗口帧率自适应**：初期固定 ~10fps 视频帧 + ~20fps 音频频谱，后续可根据窗口可见性动态调整
- **多摄像头切换**：预览窗口内切换摄像头源的功能待后续迭代
