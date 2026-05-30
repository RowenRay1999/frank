## Context

`redesign-main-panel-ui` 将界面从旧桌面布局迁移到了以 phone-frame（390×844px）为中心的三区垂直布局。新 UI 包含 Zone 1（状态栏）、Zone 2（Orb 动画 + 任务列表 + 会话面板 + Chat Overlay）、Zone 3（底部导航栏）。但原有的功能面板——设置、成员管理、人物角色、注册向导、任务看板详情——已在迁移中被移除，导致应用功能严重退化。同时，phone-frame 固定尺寸在 430×900 窗口中仅占据中央一小块区域，大量空间浪费在暗色背景上。

本设计文档定义了如何：(1) 将 UI 从 phone-frame 模型适配到全窗口弹性布局，(2) 建立通用面板系统以统一方式挂载所有原有功能。

## Goals / Non-Goals

**Goals:**
- `.main-stage` 填满窗口客户区（`100vw × 100vh`），三区高度弹性自适应
- 实现通用滑入面板（Slide-over Panel）系统，Chat Overlay 基于同一机制
- 将设置面板（LLM/TTS/音频/摄像头/隐私）、成员管理面板、人物角色面板移植到面板系统
- 将注册向导（4 步生物特征注册）作为 Modal 层移植
- Zone 3 导航栏从 `<a href>` 跳转改为触发对应面板
- 窗口恢复可缩放（resizable: true），最小 500×400，默认 800×600

**Non-Goals:**
- 不修改 Python 后端任何代码
- 不新增 IPC 事件类型（沿用现有 `window.frankAPI` 接口）
- 不重新设计面板内的表单/列表功能逻辑（保持原 app.js 的逻辑不变，仅适配 DOM 选择器）
- 不实现新的功能页面（identity.html、tasks.html 等独立页面推迟至后续变更）

## Decisions

### Decision 1: 布局模型 — 从 Phone Frame 到全窗口弹性

**选择**：移除 `.phone-frame` 包裹层，`.main-stage` 直接填满 `body`（`width: 100vw; height: 100vh; border-radius: 0`）。三区使用 flex 弹性布局保持纵向分区比例。

**CSS 变更**：
```css
body {
  background: var(--bg);  /* 不再需要 flex 居中 */
  display: block;
}
.main-stage {
  width: 100vw; height: 100vh;
  border-radius: 0;  /* 移除手机框架圆角 */
  /* 保留 radial-gradient 环境光和网格纹理 */
}
```

**替代方案**：
- A) 保留 phone-frame 但缩放至 100% → 拒绝：圆角和阴影在窗口边缘不自然
- B) 将 phone-frame 适配为可缩放容器 → 拒绝：设计意图是展示固定比例的手机形态，不适合桌面应用

**理由**：全窗口布局最大化利用屏幕空间，适合桌面环境。三区弹性布局自动适应窗口尺寸变化，无需 JS 辅助。

### Decision 2: 面板系统 — 统一 Slide-over 机制

**选择**：实现通用的 `.panel-slide` CSS 类和 `PanelManager` JS 模块。所有面板（设置、成员、人物、聊天、任务详情、通知）均为 `.panel-slide` 实例，从 Zone 2 右侧滑入，覆盖 Zone 2。

```
.zone-monitor {
  position: relative; /* 定位上下文 */
  overflow: hidden;   /* 裁剪滑入面板 */
}

.panel-slide {
  position: absolute;
  top: 0; right: 0;
  width: 100%; height: 100%;
  transform: translateX(100%);
  transition: transform var(--motion-slow) var(--ease-standard);
  z-index: 30;
}
.panel-slide.open { transform: translateX(0); }
```

**互斥管理**：同时只允许一个面板打开。`PanelManager` 维护当前激活面板的引用，打开新面板时自动关闭当前面板。

```js
const PanelManager = {
  currentPanel: null,
  open(panelEl) {
    if (this.currentPanel && this.currentPanel !== panelEl) {
      this.currentPanel.classList.remove('open');
    }
    panelEl.classList.add('open');
    this.currentPanel = panelEl;
  },
  close(panelEl) {
    panelEl.classList.remove('open');
    if (this.currentPanel === panelEl) this.currentPanel = null;
  },
  closeAll() {
    document.querySelectorAll('.panel-slide.open').forEach(p => p.classList.remove('open'));
    this.currentPanel = null;
  }
};
```

**Chat Overlay 统一**：将现有的 `.chat-overlay` 追加 `.panel-slide` 类，复用同一套滑入/关闭机制。

**替代方案**：
- A) 每个面板独立 CSS 类 → 拒绝：重复代码，不一致
- B) 使用 `<dialog>` 元素或 Modal → 拒绝：滑入式面板更适合侧边形式，不阻断主界面可见性

### Decision 3: 导航栏 — 从页面跳转到面板触发

**选择**：将 Zone 3 导航项从 `<a href="...">` 改为 `<button>` 或 `<a href="#" onclick="...">`，点击后调用 `PanelManager.open(对应面板)`。激活态（`.active`）跟随面板开关状态变化。

**映射表**：

| 导航项 | 面板 ID | 原功能 |
|---|---|---|
| 身份识别 | `#identityPanel` | 人物角色面板（身份卡 + 角色卡片 + 权限矩阵） |
| 任务看板 | `#taskDetailPanel` | 任务详情面板（完整任务列表 + 筛选 + 统计） |
| 通知中心 | `#notifPanel` | 通知面板（通知列表） |
| 设置 | `#settingsPanel` | 设置面板（LLM/TTS/音频/摄像头/隐私） |

**替代方案**：
- A) 创建独立 HTML 页面 → 拒绝：增加了页面加载延迟和状态管理复杂度，不如面板机制流畅
- B) `<a>` 保持 href 但用 JS 拦截 → 备选：可使用 `onclick="event.preventDefault(); openPanel(...)"` 以保持语义化 HTML

**选择 B 作为实现方案** —— 保持 `<a>` 标签以保留语义和无障碍特性，JS 拦截点击。

### Decision 4: 面板内容移植策略 — 提取 + 适配

**选择**：从旧 `index.html`（git 历史中的版本）提取面板 HTML 结构，从旧 `app.js` 提取对应的 JS 逻辑函数，适配新设计令牌后注入新 HTML/JS。

**移植清单**：

| 面板 | HTML 提取源 | JS 提取源 | CSS 适配 |
|---|---|---|---|
| 设置面板 | `#settings-panel` | `loadSettings`, `populateSettingsForm`, `flattenConfig`, `unflattenConfig`, 设置变更事件 | 表单控件适配新令牌：`.settings-input` → `--bg` 背景 + `--border` 边框 |
| 成员面板 | `#members-panel` + `#member-list` + `#pending-list` | `refreshMemberPanel`, `renderMemberList`, `renderPendingList`, IPC 监听 `onMemberList`/`onMemberPending` | 列表项适配新令牌 |
| 人物面板 | `#persona-panel` + `#identity-card` + `#role-cards` + `#permission-matrix` | `loadPersonaPanel`, `renderRoleCards`, `renderPermissionMatrix`, `updateIdentityCard` | 卡片网格适配新令牌 |
| 注册向导 | `#wizard-overlay` | `openWizard`, `closeWizard`, `goToStep`, IPC 监听向导事件 | Modal 覆盖层适配新令牌 |

**不移植的功能**：旧 `updateUI`、`addSystemMessage`、`togglePanel`、`closeAllPanels` 已被新架构替代，不需移植。

### Decision 5: 窗口模型 — 恢复可缩放

**选择**：修改 `createWindow()` 配置：
- `width: 800, height: 600`（默认尺寸）
- `minWidth: 500, minHeight: 400`
- `resizable: true`
- 移除 `maxWidth`/`maxHeight` 限制
- 保留 `frame: false`, `backgroundColor: '#0a0a0c'`

**理由**：桌面应用应支持用户自由调整窗口尺寸，新全窗口布局使这成为可能。

## Risks / Trade-offs

| Risk | Impact | Mitigation |
|---|---|---|
| 面板互斥逻辑 bug 导致多个面板同时打开 | UI 混乱，遮挡叠加 | PanelManager 强制单例，打开前先关闭当前；添加 CSS `z-index` 层级管理 |
| 移动 phone-frame 后 Orb 动画在宽屏上居中位置偏移 | 视觉不协调 | Orb 始终在 Zone 2 `.monitor-thinking` 中 `flex` 居中，不受窗口宽度影响 |
| 旧 JS 逻辑中的 DOM 选择器与新 HTML ID 不匹配 | 面板功能失效 | 逐一映射旧 ID 到新面板内的 DOM ID；添加 `?.` 空值防护 |
| 注册向导的摄像头/麦克风采集依赖硬件 | 无权限时向导卡在 Step 2/3 | 保留原有的权限检查和错误提示逻辑（`未检测到摄像头/麦克风`） |
| 全窗口后 `.phone-frame` 的 box-shadow 装饰丢失 | 窗口缺少立体感 | 在 `.main-stage` 顶部添加 1px 微边框（`var(--border-soft)`）作为窗口轮廓 |

## Open Questions

- 通知面板（`#notifPanel`）的内容设计？→ 初版以简单列表展示占位内容（通知标题 + 时间），后续变更完善
- 任务详情面板（`#taskDetailPanel`）与 Zone 2 内联任务列表的数据联动？→ 内联列表显示最近 4 条，详情面板显示完整列表（从 IPC `task.list` 获取）
- 窗口拖拽区域？→ 整个 Zone 1 状态栏区域设为 `-webkit-app-region: drag`，内部控件设为 `no-drag`
