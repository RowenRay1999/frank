## Why

当前 Frank 桌面应用界面（index.html）功能虽完整但视觉陈旧、交互粗糙——简陋的标题栏、静态文本卡片、基础表单控件，缺乏"AI 家庭管家"应有的现代感与科技感。设计稿 `design/main-panel.html` 已沉淀出一套成熟的视觉语言：以深色背景衬托的"手机框架"主面板、三区垂直布局（状态+监控+导航）、思考动画光球、玻璃拟态（glass morphism）、悬浮粒子动画，提供了经过验证的 UI 方向。现在是时候将设计稿落地为实际运行的 Electron 界面了。

## What Changes

- **重构整体布局**：从当前的标题栏+欢迎卡片+聊天区+工具栏的线性布局，切换为居中手机框架（390×844px）内的三区垂直布局：Zone 1 状态通知栏、Zone 2 监控区（思考动画+任务列表+会话面板）、Zone 3 底部导航栏
- **新设计系统**：以 `design/main-panel.html` 为蓝本，建立 CSS 变量驱动的设计令牌体系（oklch 色彩空间、毛玻璃效果、统一圆角与间距刻度、标准动效曲线）
- **新增思考动画光球（Orb）**：5 色阶同心圆环光球，支持呼吸动画（idle）和思考动画（active），配合扩散光环和悬浮粒子场
- **重新设计状态栏**：Zone 1 替换为两行布局——上行显示用户身份（头像+名称+角色）和通知预览，下行显示硬件状态芯片（摄像头/麦克风/屏幕录制）
- **任务列表 3 态切换**：Zone 2 底部任务区域支持 collapsed → half-expanded → full 三态循环切换，替换静态任务占位
- **内联会话面板**：Zone 2 底部的对话看板，展示会话摘要栏+最近消息气泡预览，点击展开全屏 Chat Overlay
- **Chat Overlay 对话浮层**：从右侧滑入的全屏对话面板（覆盖 Zone 2），支持消息列表、输入框、键盘快捷键（Escape 关闭、空格切换）
- **底部导航栏**：Zone 3 的 4 项导航（身份识别、任务看板、通知中心、设置）+ 分隔线，替代原工具栏按钮
- **简化窗口模型**：从当前的无边框浮动窗口 + 标题栏模式，变化为固定比例的手机框架式主面板
- **标题栏重构**：移除原自定义标题栏，窗口关闭/最小化/置顶等控制移至外部框架或托盘

## Capabilities

### New Capabilities

- `main-panel-layout`: 新主面板三区垂直布局（手机框架式居中容器，Zone 1 状态 / Zone 2 监控 / Zone 3 导航）
- `orb-thinking-animation`: 思考动画光球组件（5色阶辐射渐变、呼吸/思考双模动画、扩散光环、粒子场）
- `status-notification-bar`: 状态通知栏组件（用户身份展示、实时时钟、通知预览、硬件状态芯片）
- `task-list-panel`: 内联任务列表面板（3态折叠切换、任务行状态展示、来源标签、耗时计数）
- `inline-conversation-board`: 内联会话看板（会话摘要栏、消息气泡内联预览、展开对话入口）
- `chat-overlay`: 全屏对话浮层组件（右侧滑入、消息列表、输入框、Escape/空格快捷键）
- `bottom-nav-bar`: 底部导航栏（图标+标签路由项、激活态指示、分隔线）
- `design-token-system`: 新设计令牌体系（oklch 色彩、统一间距、毛玻璃效果、动效曲线）

### Modified Capabilities

- `ui-shell`: **BREAKING** — 窗口模型从无边框浮动窗口（360×500 compact / 800×600 full）变更为固定比例手机框架式面板；移除原自定义标题栏；状态指示器重新设计为 Zone 1 用户身份区域；消息气泡从简单 flex 布局替换为 Chat Overlay 内气泡组件；排除原有的设置面板占位、成员管理面板、注册向导面板（这些功能面板在新的导航模型下重新挂载）

## Impact

- **Affected code**:
  - `src/electron/renderer/index.html` — 完全重写 HTML 结构
  - `src/electron/renderer/styles.css` — 完全重写样式表，替换为新设计令牌体系
  - `src/electron/renderer/app.js` — 大幅修改：DOM 引用更新、面板管理逻辑调整、新增 Orb 动画控制、Chat Overlay 交互
  - `src/electron/main/main.js` — 窗口尺寸/模型可能需要调整以适配新布局
- **Affected specs**:
  - `openspec/specs/ui-shell/spec.md` — 窗口管理、标题栏、状态指示器、消息气泡等需求需 delta 更新
- **Dependencies**: 无新增外部依赖；纯 HTML/CSS/JS 变更
- **Risk**: 高 — 一次性全量替换 UI 壳，需确保现有 IPC 事件通路（状态变更、身份识别、手势等）在新 HTML 结构中正确绑定
