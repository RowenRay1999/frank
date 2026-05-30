## ADDED Requirements

### Requirement: 会话展示栏

任务列表下方 SHALL 显示会话展示栏（`.convo-bar`），包含以下元素：
- **Frank 头像**（`.convo-bar-avatar`）：28×28px 圆形，蓝色径向渐变背景（`radial-gradient(circle at 35% 35%, rgba(0,160,255,0.3), transparent 55%)`），暖橙色半透明底色（`var(--accent-soft)`），1.5px 蓝色边框（`rgba(0, 113, 227, 0.3)`），居中显示字母 "F"，带蓝色外发光（`0 0 12px rgba(0, 113, 227, 0.12)`）
- **会话信息**（`.convo-bar-info`）：包含会话主题（`.convo-bar-topic`，11px，weight 600，`var(--fg)`，单行省略）和元信息行（`.convo-bar-meta`，等宽字体 10px，`var(--muted)`，如 "共 4 条消息 · 2 分钟前"）
- **展开按钮**（`.convo-bar-expand`）：药丸形按钮，暖橙色半透明背景（`var(--accent-soft)`），橙色文字（`var(--accent)`），10px，weight 600，文本"展开" + 右箭头 SVG 图标。悬停时变为实心橙色背景（`var(--accent)`）、白色文字（`var(--accent-on)`）

#### Scenario: 会话展示栏显示最近对话

- **WHEN** 最近一次对话主题为"明天日程安排 · 提醒设置"，共 4 条消息
- **THEN** 会话展示栏显示 Frank 头像（字母 F）、主题文本"明天日程安排 · 提醒设置"、元信息"共 4 条消息 · 2 分钟前"和"展开"按钮

### Requirement: 对话气泡内联预览

会话展示栏下方 SHALL 显示最近对话消息气泡的内联预览区域（`.convo-bubbles`）。预览区域：
- 最大高度 170px，超出可滚动（细滚动条 3px 宽，`var(--border-soft)` 色）
- 消息气泡宽度最大 88%
- 气泡支持两种对齐方向：
  - **Frank 消息**（`.convo-bubble.frank`）：左对齐，`var(--surface-elevated)` 背景，`1px solid var(--border)` 边框，左下角小圆角（`var(--radius-sm)`），文本色 `var(--fg)`
  - **用户消息**（`.convo-bubble.user`）：右对齐，`var(--accent)` 背景，白色文字（`var(--accent-on)`），右下角小圆角

每条气泡 SHALL 包含：
- 发送者标签（`.convo-bubble-sender`）：等宽字体 9px，uppercase，opacity 0.55
- 消息文本：11px，line-height 1.45
- 时间戳（`.convo-bubble-time`）：等宽字体 8px，opacity 0.4，右对齐，tabular-nums

气泡进入动画 SHALL 为 `convo-bubble-in`：`opacity: 0; translateY(4px)` → `opacity: 1; translateY(0)`，0.25s，`var(--ease-standard)`。

#### Scenario: 预览最近对话气泡

- **WHEN** 最近对话包含 4 条消息（用户→Frank→用户→Frank）
- **THEN** 气泡预览区依次显示 4 条气泡，用户消息右对齐橙色背景，Frank 消息左对齐深色背景

#### Scenario: 气泡数量超过可视区域可滚动

- **WHEN** 对话气泡总高度超过 170px
- **THEN** 预览区域出现细滚动条（3px），用户可滚动查看所有气泡

### Requirement: 展开按钮触发 Chat Overlay

点击会话展示栏的"展开"按钮 SHALL 打开 Chat Overlay 对话浮层。

#### Scenario: 点击展开打开完整对话

- **WHEN** 用户点击会话展示栏的"展开"按钮
- **THEN** Chat Overlay 从右侧滑入，显示完整对话历史

### Requirement: 折叠态隐藏

当 Zone 2 的任务列表处于 collapsed 状态时，会话面板（`.convo-section`）SHALL 隐藏（`display: none`）。

#### Scenario: 折叠态隐藏会话面板

- **WHEN** 任务列表区域切换至 collapsed 状态
- **THEN** 会话展示栏和气泡预览区域均隐藏
