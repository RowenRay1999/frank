## ADDED Requirements

### Requirement: Chat Overlay 布局

Chat Overlay（`.chat-overlay`）SHALL 作为一个绝对定位面板覆盖在 Zone 2 区域之上（`z-index: 30`），宽度 100%，高度 100%。默认状态 SHALL 为隐藏（`transform: translateX(100%)`），打开时 SHALL 向左滑入（`transform: translateX(0)`），过渡时间 `var(--motion-slow)`（400ms），缓动 `var(--ease-standard)`。

Overlay 背景 SHALL 为毛玻璃效果（`var(--surface-glass)` + `backdrop-filter: blur(28px)`），左侧带 1px 边框（`var(--border)`），左侧外阴影 `-8px 0 32px rgba(0,0,0,0.5)`。

内部纵向布局（flex column）：
1. **头部**（`.chat-overlay-header`）：标题 "Frank · 对话" + 关闭按钮
2. **消息区域**（`.chat-overlay-messages`）：弹性高度，可滚动
3. **输入栏**（`.chat-input-bar`）：文本输入框 + 发送按钮

#### Scenario: Overlay 默认隐藏

- **WHEN** 主面板渲染
- **THEN** Chat Overlay 位于 Zone 2 右侧外部（translateX(100%)），不可见

#### Scenario: 打开 Overlay 滑入

- **WHEN** 用户点击光球或"展开"按钮
- **THEN** Chat Overlay 以 400ms ease 动画从右向左滑入，覆盖整个 Zone 2

### Requirement: 头部区域

Overlay 头部 SHALL 包含：
- **标题**：font-family `var(--font-display)`，字号 `var(--text-md)`（16px），weight 600，letter-spacing `var(--tracking-display)`
- **关闭按钮**（`.chat-close`）：28×28px 圆形，`var(--fg-2)` 色 "✕" 图标。悬停时背景 `var(--border-soft)`，文字色 `var(--fg)`

#### Scenario: 点击关闭按钮退出

- **WHEN** Chat Overlay 处于打开状态，用户点击关闭按钮（✕）
- **THEN** Overlay 向右滑出隐藏

### Requirement: 消息气泡

消息区域 SHALL 展示对话历史气泡（`.chat-bubble`），气泡最大宽度 82%，内边距 12px 16px，圆角 `var(--radius-lg)`（18px），字号 `var(--text-sm)`（13px），行高 1.5。

**Frank 消息**（`.chat-bubble.frank`）：
- 左对齐（`align-self: flex-start`）
- 背景 `var(--surface-elevated)`
- 边框 `1px solid var(--border)`
- 左下角小圆角 `var(--radius-sm)`
- 文本色 `var(--fg)`

**用户消息**（`.chat-bubble.user`）：
- 右对齐（`align-self: flex-end`）
- 背景 `var(--accent)`（暖橙色）
- 文本色 `var(--accent-on)`（白色）
- 右下角小圆角 `var(--radius-sm)`

气泡进入动画：`bubble-in` — `opacity: 0; translateY(8px)` → `opacity: 1; translateY(0)`，0.3s，`var(--ease-standard)`。

#### Scenario: 用户消息显示为橙色右对齐气泡

- **WHEN** 用户发送消息"帮我查一下明天下午的日程"
- **THEN** 消息区域底部出现右对齐的橙色气泡，内容为 "帮我查一下明天下午的日程"

#### Scenario: Frank 消息显示为深色左对齐气泡

- **WHEN** LLM 返回回复文本
- **THEN** 消息区域底部出现左对齐的深色气泡，内容为回复文本

### Requirement: 消息区域滚动

消息区域 SHALL 启用纵向滚动（`overflow-y: auto`）。新消息到达时 SHALL 自动滚动至底部。消息间间距 SHALL 为 `var(--space-4)`（16px）。

#### Scenario: 新消息自动滚动到底部

- **WHEN** 新消息添加到消息列表
- **THEN** 消息容器自动滚动至最底部，最新消息完全可见

### Requirement: 输入栏

底部输入栏 SHALL 包含：
- **文本输入框**（`.chat-input`）：`flex: 1`，内边距 10px 14px，背景 `var(--bg)`，`1px solid var(--border)` 边框，`border-radius: var(--radius-full)`（药丸形），`var(--fg)` 色文字，字号 `var(--text-sm)`，placeholder "输入消息…"。聚焦时边框色变更为 `var(--accent)`，外发光 `0 0 0 3px var(--accent-soft)`
- **发送按钮**（`.chat-send`）：38×38px 圆形，`var(--accent)` 背景，白色文字，居中显示纸飞机 SVG 图标。悬停时背景变更为 `var(--accent-hover)`

#### Scenario: 输入框聚焦高亮

- **WHEN** 用户点击输入框
- **THEN** 输入框边框变为橙色，出现 3px 橙色外发光

#### Scenario: 点击发送按钮

- **WHEN** 用户在输入框中输入文本后点击发送按钮
- **THEN** 文本作为用户消息添加到消息列表，输入框清空

### Requirement: 键盘快捷键

Chat Overlay SHALL 支持以下键盘快捷键：
- **Escape**：关闭 Overlay（如已打开）
- **空格**（当焦点在 document.body 时）：切换 Overlay 打开/关闭状态

#### Scenario: Escape 关闭 Overlay

- **WHEN** Chat Overlay 打开，用户按下 Escape 键
- **THEN** Overlay 关闭

#### Scenario: 空格键切换 Overlay

- **WHEN** 焦点在页面主体（非输入框），用户按下空格键
- **THEN** 如果 Overlay 已关闭则打开，如果已打开则关闭

### Requirement: Enter 键发送消息

当输入框聚焦时，按下 Enter 键 SHALL 触发消息发送（等同于点击发送按钮）。

#### Scenario: Enter 键发送

- **WHEN** 用户在输入框中输入文本并按下 Enter 键
- **THEN** 输入文本作为用户消息添加到消息列表，输入框清空
