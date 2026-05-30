## ADDED Requirements

### Requirement: 任务列表区域布局

Zone 2 下部（`.monitor-bottom`）SHALL 包含任务列表区域，由以下元素组成：
- **区域头部**（`.section-header`）：左侧显示 "执行状态" 标题（等宽字体 uppercase 10px，`var(--muted)`）+ 任务计数徽章（`.section-count`），右侧显示"查看全部"链接和一个 3 态切换按钮
- **任务列表滚动区**（`.task-list-scroll`）：可滚动的任务行列表，flex column，gap 2px
- **半展开提示**（`.task-half-hint`）：仅在 half-expanded 状态可见，显示"展开更多 ▾"，点击后切换至 full 状态

整个 `.monitor-bottom` 区域 SHALL 应用半透明背景（`rgba(29, 29, 31, 0.30)`）和毛玻璃效果（`backdrop-filter: blur(12px)`）。

#### Scenario: 任务列表区域渲染

- **WHEN** 主面板渲染
- **THEN** Zone 2 下部显示"执行状态"标题、任务计数（如"4"）、查看全部链接和切换按钮

### Requirement: 3 态折叠切换

任务列表区域 SHALL 支持 3 种状态，通过点击切换按钮（`.task-toggle`）循环切换：
1. **collapsed**：仅显示 section-header（高度约 36px），任务列表和会话面板隐藏
2. **half-expanded**（默认）：任务列表区域限制最大高度 160px，底部显示"展开更多 ▾"提示
3. **full**：任务列表区域无高度限制，显示所有内容，会话面板完整可见

切换按钮中的 SVG 箭头图标 SHALL 根据状态旋转：
- collapsed：箭头向下（0deg，列表隐藏）
- half-expanded：箭头向上（180deg）
- full：箭头向下（0deg，再次点击变为 collapsed）

#### Scenario: 默认半展开状态

- **WHEN** 主面板首次渲染
- **THEN** 任务列表处于 half-expanded 状态，最多显示约 160px 高度，底部显示"展开更多 ▾"提示

#### Scenario: 点击折叠任务列表

- **WHEN** 用户在 half-expanded 状态下点击切换按钮
- **THEN** 任务列表切换至 full 状态，所有任务行可见，会话面板完整展开

#### Scenario: 再次点击完全折叠

- **WHEN** 用户在 full 状态下点击切换按钮
- **THEN** 任务列表切换至 collapsed 状态，仅显示 section-header，"展开更多"提示隐藏

### Requirement: 任务行样式

每条任务行（`.task-row`）SHALL 使用 4 列 grid 布局：状态图标（18px） + 任务文本（`flex: 1`） + 来源标签 + 耗时。

**状态图标**（`.task-status-icon`）支持 4 种样式：
- **running**：蓝色半透明背景（`rgba(100, 210, 255, 0.15)`），蓝色文字（`var(--info)`），脉冲动画（opacity 1→0.45→1，周期 1.4s），内含旋转 spinner（border-top 蓝色，0.9s 旋转）
- **pending**：灰色背景（`var(--border-soft)`），灰色文字（`var(--muted)`），内含时钟图标
- **done**：绿色半透明背景（`rgba(48, 209, 88, 0.15)`），绿色文字（`var(--success)`），内含对勾图标
- **failed**：红色半透明背景（`rgba(255, 69, 58, 0.15)`），红色文字（`var(--danger)`）

**任务文本**（`.task-row-text`）：11px，`var(--fg)`，单行省略。已完成任务文本色为 `var(--muted)`。

**来源标签**（`.task-row-source`）：等宽字体 9px，药丸形，`var(--border-soft)` 背景，`var(--muted)` 色。

**耗时**（`.task-row-elapsed`）：等宽字体 10px，`var(--muted)`，tabular-nums，最小宽度 38px，右对齐。

已完成任务行添加 `.done-row` 类。

#### Scenario: 运行中任务显示 spinner

- **WHEN** 有一个正在执行的任务"人脸识别 · 爸爸身份匹配中"
- **THEN** 任务行显示蓝色旋转 spinner、任务文本、来源标签（如"sys"）和实时耗时

#### Scenario: 已完成任务显示对勾

- **WHEN** 任务"日程查询"执行完毕
- **THEN** 任务行状态图标变为绿色对勾，文本颜色变灰

### Requirement: 任务行点击交互

点击任意任务行 SHALL 打开 Chat Overlay 对话浮层。

#### Scenario: 点击任务行打开对话

- **WHEN** 用户点击任意任务行
- **THEN** Chat Overlay 从右侧滑入展开

### Requirement: 半展开提示点击

在半展开状态下，点击 `.task-half-hint`（"展开更多 ▾"）SHALL 将任务列表切换至 full 状态。

#### Scenario: 点击展开更多

- **WHEN** 任务列表处于 half-expanded 状态，用户点击"展开更多 ▾"
- **THEN** 任务列表切换至 full 状态，完整内容可见
