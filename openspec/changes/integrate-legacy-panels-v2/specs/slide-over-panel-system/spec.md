## ADDED Requirements

### Requirement: 面板容器基础样式

系统 SHALL 提供一个通用的滑入面板 CSS 类（`.panel-slide`），面板 SHALL：
- 定位于 Zone 2（`.zone-monitor`）内部，`position: absolute; top: 0; right: 0; width: 100%; height: 100%`
- 默认隐藏：`transform: translateX(100%)`
- 打开时滑入：添加 `.open` 类 → `transform: translateX(0)`，过渡时间 `var(--motion-slow)`（400ms），缓动 `var(--ease-standard)`
- 背景为毛玻璃效果：`background: var(--surface-glass); backdrop-filter: blur(28px); -webkit-backdrop-filter: blur(28px)`
- 左侧边框：`border-left: 1px solid var(--border)`
- 左侧外阴影：`box-shadow: -8px 0 32px rgba(0,0,0,0.5)`
- z-index: 30

面板内容采用 flex column 布局：头部（`.panel-slide-header`）+ 内容区（`.panel-slide-body`，`flex: 1; overflow-y: auto`）+ 可选底部栏（`.panel-slide-footer`）。

#### Scenario: 面板默认隐藏

- **WHEN** 主面板渲染
- **THEN** 所有 `.panel-slide` 元素位于 Zone 2 右侧外部，不可见

#### Scenario: 面板滑入

- **WHEN** 调用 `PanelManager.open(panelEl)` 打开某个面板
- **THEN** 该面板以 400ms ease 动画从右侧滑入，覆盖 Zone 2 全部区域

### Requirement: 面板头部

每个面板 SHALL 包含头部区域（`.panel-slide-header`），flex 水平布局包含：
- 标题（`.panel-slide-title`）：font-family `var(--font-display)`，字号 `var(--text-md)`，weight 600
- 关闭按钮（`.panel-slide-close`）：28×28px 圆形，`var(--fg-2)` 色 ✕ 图标，悬停时背景 `var(--border-soft)` 文字 `var(--fg)`

#### Scenario: 面板头部显示标题和关闭按钮

- **WHEN** 设置面板打开
- **THEN** 面板顶部显示 "设置" 标题和 ✕ 关闭按钮

#### Scenario: 点击关闭按钮

- **WHEN** 用户点击面板头部的 ✕ 按钮
- **THEN** 面板向右滑出隐藏

### Requirement: 面板互斥管理

系统 SHALL 通过 `PanelManager` JS 对象管理面板的打开与关闭：

- `PanelManager.open(panelEl)`：打开指定面板。若已有其他面板打开，先关闭已打开面板，再滑入新面板
- `PanelManager.close(panelEl)`：关闭指定面板，若该面板是当前面板则清除引用
- `PanelManager.closeAll()`：关闭所有已打开面板
- `PanelManager.isOpen(panelEl)`：返回指定面板是否已打开

Escape 键 SHALL 关闭当前已打开的面板（委托给 `PanelManager.closeAll()` 或关闭当前面板）。

#### Scenario: 同时只允许一个面板打开

- **WHEN** 设置面板已打开，用户点击触发人物面板
- **THEN** 设置面板先关闭，人物面板随后滑入

#### Scenario: Escape 关闭面板

- **WHEN** 设置面板已打开，用户按下 Escape 键
- **THEN** 设置面板关闭

### Requirement: Chat Overlay 统一

现有的 `.chat-overlay` SHALL 同时拥有 `.panel-slide` 类，复用面板系统的滑入/关闭机制。Chat Overlay 的 `#chatOverlay` 元素 SHALL 添加 `class="panel-slide"`。`openChat()` / `closeChat()` 函数 SHALL 内部委托给 `PanelManager.open(chatOverlay)` / `PanelManager.close(chatOverlay)`。

#### Scenario: Chat Overlay 通过 PanelManager 打开

- **WHEN** 用户点击 Orb 光球
- **THEN** `PanelManager.open(chatOverlay)` 被调用，Chat Overlay 滑入，若有其他面板打开则先关闭

#### Scenario: Chat Overlay 与其他面板互斥

- **WHEN** Chat Overlay 已打开，用户点击导航触发设置面板
- **THEN** Chat Overlay 先关闭，设置面板随后滑入

### Requirement: 面板内容区域滚动

面板内容区域（`.panel-slide-body`）SHALL 在内容溢出时启用纵向滚动（`overflow-y: auto`），滚动条样式 SHALL 与全局一致（6px 宽，`var(--border-soft)` 色滑块，`var(--muted)` 色悬停）。

内边距 SHALL 为 `padding: var(--space-5)`。

#### Scenario: 设置表单内容过长时可滚动

- **WHEN** 设置面板中有大量表单控件，总高度超过面板可用空间
- **THEN** 内容区域出现滚动条，用户可滚动查看所有设置项
