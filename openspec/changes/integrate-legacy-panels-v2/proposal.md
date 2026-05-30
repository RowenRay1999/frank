## Why

`redesign-main-panel-ui` 完成了从旧 UI 到新视觉语言的迁移，但遗留了两个关键缺口：(1) 原有的功能面板（设置、成员管理、人物角色、注册向导、任务看板）被移除后未在新 UI 中重新挂载，导致应用功能严重退化；(2) 390×844px 的手机框架无法填满窗口可用空间，在桌面环境中显得局促且浪费屏幕面积。现在是时候将原有功能对应到新 UI 架构中，并让布局适配桌面窗口形态。

## What Changes

- **窗口自适应布局**：移除 `.phone-frame` 固定尺寸容器，将 `.main-stage` 改为填满窗口客户区的弹性布局（`width: 100vw; height: 100vh`），圆角和阴影装饰改为可选的窗口级样式
- **面板系统（Slide-over Panel）**：在 Zone 2 区域实现通用滑入面板机制（与 Chat Overlay 同模式），从右侧滑入，覆盖 Zone 2。面板通过 Zone 3 导航栏触发
- **设置面板迁移**：将原 `#settings-panel`（LLM/TTS/音频设备/摄像头/隐私设置）移植为新 panel，保留全部表单控件、自动保存、设备列表加载、分组折叠功能
- **成员管理面板迁移**：将原 `#members-panel`（已识别成员列表 + 待识别访客列表 + 添加成员入口）移植为新 panel，保留全部 IPC 事件监听和列表渲染
- **人物角色面板迁移**：将原 `#persona-panel`（身份识别卡 + 角色卡片 + 权限矩阵）移植为新 panel，保留点击展开技能详情交互
- **注册向导迁移**：将原 `#wizard-overlay`（4 步生物特征注册流程）移植为 Modal 叠加层，保留步骤导航、面部/声纹采集进度、表单验证
- **手势/暂停/错误 UI 保留**：手势浮层 toast、暂停横幅、错误 toast 已在上次变更中保留，本次确认在窗口自适应布局中正常工作
- **Zone 3 导航栏功能化**：每个导航项点击后触发对应面板（而非 `href` 跳转独立页面），激活态高亮切换

## Capabilities

### New Capabilities

- `window-adaptive-layout`: 窗口自适应布局 — `.main-stage` 填满窗口客户区，移除 phone-frame 固定尺寸约束，三区弹性高度自适应
- `slide-over-panel-system`: 滑入式面板系统 — 通用面板容器（右侧滑入、毛玻璃背景、头部标题+关闭按钮、内容区弹性滚动），Chat Overlay 也统一使用此机制

### Modified Capabilities

- `main-panel-layout`: 移除 phone-frame 固定容器，`.main-stage` 改为全窗口弹性布局，Zone 1/2/3 比例保持但高度自适应窗口
- `bottom-nav-bar`: 导航项从 `<a href>` 页面跳转改为点击触发对应滑入面板，激活态随面板切换联动
- `status-notification-bar`: 通知预览点击从 `location.href` 改为触发通知面板
- `task-list-panel`: "查看全部"链接从 `<a href="tasks.html">` 改为触发任务详情面板
- `chat-overlay`: 重构为基于通用 panel 系统的实例，保持全部现有交互行为
- `ui-shell`: 更新窗口管理需求 — 窗口变为可缩放（resizable: true），最小尺寸 500×400，默认尺寸 800×600；移除 phone-frame 外壳；保留托盘逻辑

## Impact

- **Affected code**:
  - `src/electron/renderer/index.html` — 新增设置/成员/人物/任务详情/通知面板 HTML；移除 phone-frame 包裹层；Zone 3 导航项改为 button 触发面板
  - `src/electron/renderer/styles.css` — 新增 `.panel-slide` 滑入面板样式；调整 `.main-stage` 为全窗口弹性布局；添加表单/列表/卡片组件样式（从旧 styles.css 提取并适配新设计令牌）；移除 phone-frame 相关样式
  - `src/electron/renderer/app.js` — 新增面板管理器（`openPanel`/`closePanel`/`closeAllPanels`）；移植设置/成员/人物/向导的全部 JS 逻辑；更新 Zone 3 导航项为面板触发
  - `src/electron/main/main.js` — 窗口恢复可缩放 + 默认 800×600 + 最小 500×400
- **Affected specs**:
  - `openspec/changes/redesign-main-panel-ui/specs/` — 新增的 main-panel-layout、bottom-nav-bar、chat-overlay、task-list-panel、status-notification-bar 规格需 delta 更新
  - `openspec/specs/ui-shell/spec.md` — 窗口管理需求再次变更
- **Dependencies**: 依赖 `redesign-main-panel-ui` 已完成的新 UI 代码作为基线
- **Risk**: 中 — 面板系统与现有 Chat Overlay 共享滑入机制，需确保同时只有一个面板打开（互斥锁）
