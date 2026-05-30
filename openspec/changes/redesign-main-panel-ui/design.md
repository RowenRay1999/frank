## Context

当前 Frank Electron 渲染进程（`src/electron/renderer/`）采用传统的无边框窗口+标题栏+内容区域布局，视觉风格为深蓝紫色调（`#1a1a2e` 背景、`#4a9eff` 强调色）。功能逻辑通过 IPC（contextBridge）与主进程通信，涵盖状态机变更、身份识别、手势检测等事件流。

设计稿 `design/main-panel.html` 在 lookdev 环境中验证了一种全新的视觉方向：
- **容器模型**：居中手机框架（390×844px），暗色背景衬托
- **色彩体系**：oklch 色彩空间，暖橙色（oklch(58% 0.18 42)）为主强调色
- **布局模型**：三区垂直分区（Status 固定头 / Monitor 弹性中 / Routing 固定底）
- **材质系统**：毛玻璃（backdrop-filter: blur）、径向渐变光晕、网格纹理
- **动画语言**：光球呼吸（radial-gradient scale）、光环扩散（ring-expand）、粒子漂浮

本设计文档定义了如何将设计稿落地为可运行的 Electron UI，保持现有 IPC 通路不变。

## Goals / Non-Goals

**Goals:**
- 将 `design/main-panel.html` 的 HTML 结构、CSS 样式、交互逻辑移植到 `src/electron/renderer/` 的三个文件中
- 建立完整的设计令牌（design tokens）体系，替代当前的硬编码 CSS 变量
- 保持所有现有 IPC 事件通路（`onStateChanged`、`onIdentityConfirmed`、`onGestureDetected` 等）在新 UI 中正常工作
- 实现 Orb 思考动画的三态控制（idle / thinking / active）
- 实现任务列表 3 态折叠切换（collapsed / half / full）
- 实现 Chat Overlay 滑入/滑出交互
- 窗口模型从可变尺寸调整为固定比例框架

**Non-Goals:**
- 不修改 Python 后端任何代码
- 不新增 IPC 事件类型（沿用现有 `window.frankAPI` 接口）
- 不实现成员管理、设置面板等侧边面板的功能（这些面板将在后续单独变更中重新挂载到新导航模型）
- 不修改 Electron 主进程的托盘逻辑
- 不实现移动端响应式——UI 固定为桌面端手机框架

## Decisions

### Decision 1: 容器模型 — 居中 Phone Frame

**选择**：窗口内部渲染一个固定 390×844px 的 `.phone-frame` 容器，居中于窗口客户区。窗口本身尺寸为 430×900px（含边框阴影 padding）。

**替代方案**：
- A) 保持当前可变尺寸窗口，直接嵌入三区布局 → 拒绝：设计稿的视觉冲击力依赖于固定比例框架和背景衬托
- B) 让窗口本身变为 390×844px 无边框 → 拒绝：太小难以操作，缺乏桌面应用的体量感

**理由**：Phone frame 模型是设计稿的核心视觉特征。窗口略大于框架尺寸，背景暗色衬托，框架带多层 box-shadow 营造悬浮感。这种模型在整个应用生命周期中保持不变，无需响应式断点。

### Decision 2: 设计令牌体系 — oklch CSS 变量

**选择**：以设计稿中的 oklch 色彩值为基础，建立两套变量组：
1. **原始色值**（Primitives）：`--color-orange-*`、`--color-warm-white` 等
2. **语义令牌**（Semantic）：`--bg`、`--fg`、`--accent`、`--border`、`--muted` 等

```
:root {
  /* Primitives — oklch */
  --orange-100: oklch(98% 0.005 80);
  --orange-200: oklch(88% 0.06 65);
  --orange-300: oklch(76% 0.12 55);
  --orange-400: oklch(64% 0.18 48);
  --orange-500: oklch(52% 0.20 38);

  /* Semantic */
  --bg: #0a0a0c;
  --surface-glass: rgba(22, 22, 24, 0.75);
  --surface-elevated: rgba(29, 29, 31, 0.85);
  --fg: #f5f5f7;
  --fg-2: #98989d;
  --muted: #636366;
  --accent: oklch(64% 0.18 48);
  --accent-soft: rgba(255, 149, 0, 0.12);
  --accent-hover: oklch(58% 0.20 42);
  --accent-on: #ffffff;
  --border: rgba(255, 255, 255, 0.08);
  --border-soft: rgba(255, 255, 255, 0.05);

  /* Spacing scale */
  --space-1: 4px; --space-2: 8px; --space-3: 12px;
  --space-4: 16px; --space-5: 20px;

  /* Typography */
  --font-display: 'SF Pro Display', 'Segoe UI', sans-serif;
  --font-mono: 'SF Mono', 'Consolas', monospace;
  --text-xs: 11px; --text-sm: 13px; --text-md: 16px;

  /* Radii */
  --radius-sm: 6px; --radius-md: 12px; --radius-lg: 18px;
  --radius-full: 9999px;

  /* Motion */
  --motion-fast: 150ms; --motion-base: 250ms; --motion-slow: 400ms;
  --ease-standard: cubic-bezier(0.2, 0, 0, 1);
}
```

**理由**：原 `styles.css` 使用浅层的 `--bg-primary`、`--accent-blue` 等变量，语义不完整且色彩体系为蓝色调。新体系完整覆盖间距、圆角、动效，并与橙色视觉主题对齐。原始值+语义令牌的二级架构便于未来主题切换。

### Decision 3: HTML 结构 — 全量替换

**选择**：完全重写 `index.html` 的 `<body>` 内容，从 design/main-panel.html 移植 HTML 结构。保留 `<script src="app.js">` 引用。

**结构映射**：

| 原 HTML 元素 | 新 HTML 元素 | 说明 |
|---|---|---|
| `#title-bar` | 移除 | 窗口控制移至 Electron 主进程/托盘 |
| `#welcome-card` | `.zone-status` (Zone 1) | 欢迎语信息整合到状态栏的用户身份区域 |
| `#chat-area` + `#input-area` | `.chat-overlay` (Zone 2 浮层) | 聊天功能收拢到滑入式浮层 |
| `#toolbar` | `.zone-routing` (Zone 3) | 导航项从文本按钮变为图标+标签 |
| `#settings-panel` 等 | 暂缺 | 设置/成员/人物面板在后续变更中重新挂载 |
| (无) | `.monitor-thinking` (Zone 2 top) | 新增 Orb 思考动画 |
| (无) | `.monitor-bottom` (Zone 2 bottom) | 新增任务列表+会话面板 |

**理由**：新旧 HTML 结构差异过大，增量修改会产生不可维护的过渡代码。全量替换最为干净。原 `app.js` 中的面板管理和 IPC 监听逻辑需对应更新。

### Decision 4: 脚本架构 — 渐进增强

**选择**：重写 `app.js`，保持以下架构层次：
1. **DOM 引用层**（顶部）：所有 `getElementById` / `querySelector` 集中声明
2. **IPC 事件绑定层**（中部）：`window.frankAPI.on*` 回调注册
3. **UI 更新函数层**（下部）：`updateStatusBar()`、`setOrbState()`、`addChatMessage()` 等
4. **交互处理层**（底部）：click/keydown 事件监听

**保留的 IPC 接口**：
- `onStateChanged` → 更新 Zone 1 状态指示、Orb 动画状态
- `onIdentityConfirmed` → 更新 Zone 1 用户身份显示
- `onFaceDetected` / `onFaceLost` → 更新 Zone 1 硬件芯片状态
- `onWakeWord` → Orb 进入 thinking 动画
- `onGestureDetected` → 保留手势浮层 toast
- `onError` → 保留错误 toast

**理由**：脚本逻辑与 HTML 结构强耦合，无法复用原 `app.js` 中的 DOM 选择器。但 IPC 接口不变，只需将事件响应逻辑映射到新的 DOM 节点。

### Decision 5: 窗口管理 — 简化为固定尺寸

**选择**：Electron BrowserWindow 固定为 430×900px，不可缩放（`resizable: false`），无边框（`frame: false`），居中显示。移除 `btn-expand`（展开切换）和 `btn-always-on-top`（窗口置顶）按钮（置顶能力保留在托盘菜单）。

**窗口尺寸计算**：
- 内容区：390×844px（phone-frame）
- 窗口 padding：左右各 20px，上下各 28px（容纳背景阴影）
- 总窗口：430×900px

**替代方案**：
- 保留可变尺寸和展开模式 → 拒绝：phone-frame 设计依赖固定比例，缩放会破坏视觉效果

**理由**：新设计语言的核心是"精致小面板"而非"可伸缩桌面窗口"。固定尺寸简化了 CSS 布局，消除了响应式复杂度。用户通过系统托盘管理窗口显示/隐藏。

### Decision 6: CSS 文件策略 — 单文件全量替换

**选择**：完全重写 `styles.css`，不保留任何旧样式规则。新文件按以下分区组织：
1. 设计令牌（CSS 变量 `:root`）
2. 基础重置（reset / body / backdrop）
3. Phone Frame 容器
4. Zone 1 — 状态通知栏（`.zone-status`）
5. Zone 2 — 监控区（`.zone-monitor`、Orb、Task List、Convo Board）
6. Zone 3 — 导航栏（`.zone-routing`）
7. Chat Overlay（`.chat-overlay`）
8. 动画关键帧（`@keyframes`）
9. 浮层/Toast（gesture toast、error toast）

**理由**：两个版本的样式共享度极低（不同的色彩体系、布局模型、组件类型），保留旧规则只会增加文件大小和维护困惑。

## Risks / Trade-offs

| Risk | Impact | Mitigation |
|---|---|---|
| IPC 事件在新 DOM 中绑定失败 | 状态指示器不更新、Orb 不动、身份不显示 | 保持 `window.frankAPI` 接口不变；逐个验证每个 IPC 回调的 DOM 目标存在性，添加 `?.` 防护 |
| 固定 430×900 窗口在小屏笔记本上过大 | 1366×768 屏幕被窗口占据约 60% 高度 | 允许用户通过托盘菜单切换到更小的窗口模式（后续迭代）；当前 MVP 仅提供固定尺寸 |
| 一次性全量替换导致 merge conflict | 若 `develop-base-v0` 分支有并行 UI 变更 | 本变更作为 UI 的唯一入口点，建议合并前先冻结其他 UI 变更 |
| 移除侧边面板入口（设置/成员/人物） | 用户无法访问现有功能面板 | Zone 3 导航中的"设置"和"身份识别"链接指向占位页面（`settings.html`、`identity.html`），后续变更补充实现 |
| CSS 动画性能 | Orb 呼吸动画 + 粒子 + 光环可能在高 DPI 下掉帧 | 所有动画使用 `transform` 和 `opacity`（GPU 加速），粒子数量控制在 8 个以内 |

## Open Questions

- 窗口拖拽：无边框窗口如何实现拖动？→ 建议整个 `.phone-frame` 外部区域设为可拖拽（`-webkit-app-region: drag`），框架内部取消拖拽
- 标题栏最小化/关闭按钮放置位置？→ 在 `.phone-frame` 外部左上角放置一个小型控制条
- 设置面板、成员面板、人物面板的导航目标页面何时实现？→ 本变更仅搭建导航框架，目标页面（`settings.html`、`identity.html`、`notifications.html`、`tasks.html`）在后续变更中独立实现
