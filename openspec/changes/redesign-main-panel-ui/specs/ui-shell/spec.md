## MODIFIED Requirements

### Requirement: 窗口管理

系统 SHALL 在 Electron 主进程中创建一个固定尺寸的无边框窗口，尺寸为 430×900px。窗口 SHALL 不可缩放（`resizable: false`），初始居中显示。窗口位置 SHALL 在会话间持久化（使用 electron-store 或配置文件存储）。窗口内部渲染一个 390×844px 的手机框架式主面板容器，居中于窗口客户区，窗口客户区背景为深色 `#0a0a0c`。

系统 MUST 提供系统托盘图标与右键菜单（显示/隐藏窗口、退出）。点击窗口关闭按钮 SHALL 将应用最小化至托盘而非任务栏。不再提供"总在最前"切换按钮和展开/紧凑模式切换——窗口模型从可变尺寸简化为固定比例框架。

#### Scenario: 默认启动尺寸为固定面板

- **WHEN** 用户首次启动 Frank
- **THEN** 窗口以 430×900px 呈现，内部显示 390×844px 的手机框架主面板

#### Scenario: 窗口不可手动缩放

- **WHEN** 用户尝试拖拽窗口任意边缘或角落
- **THEN** 窗口尺寸不发生变化（resizable: false）

#### Scenario: 窗口位置被持久化

- **WHEN** 用户调整窗口位置后关闭并重新启动 Frank
- **THEN** 窗口恢复至上次关闭时的屏幕位置

#### Scenario: 关闭窗口最小化到托盘

- **WHEN** 用户点击窗口的关闭按钮
- **THEN** 窗口隐藏，应用继续在系统托盘运行

## REMOVED Requirements

### Requirement: 自定义标题栏

**Reason**: 新设计采用固定比例手机框架式面板，不再需要传统的桌面标题栏。窗口控制（关闭/最小化）通过托盘菜单和外置控制条实现。

**Migration**: 移除 `#title-bar` HTML 元素及相关 CSS/JS；窗口拖动通过 `.phone-frame` 外部区域实现（`-webkit-app-region: drag`）；标题文本信息（状态指示）整合到 Zone 1 状态栏的用户身份区域。

### Requirement: 状态指示器

**Reason**: 原标题栏左侧的彩色圆点状态指示器被替换为 Zone 2 中 Orb 光球的动画状态和 Zone 1 中用户身份区域的状态信息展示。

**Migration**: 移除 `#status-dot` 元素及相关 CSS 动画；系统状态（Idle/Aware/Auth/Chat/Degraded）通过 Zone 2 Orb 光球动画模式（breathing/thinking）和 Zone 1 状态标签文本可视化传达。

### Requirement: 功能型聊天面板（原聊天面板占位）

**Reason**: 原聊天面板的线性消息列表+输入状态区域，被 Chat Overlay 滑入式对话浮层替换。消息气泡样式、滚动行为和输入交互在新的 Chat Overlay 中重新实现。

**Migration**: 移除 `#welcome-card`、`#chat-area`、`#message-list`、`#input-area`、`#input-status`；对话功能移至 `.chat-overlay`；欢迎语信息整合到 Zone 1 用户身份区域。

### Requirement: 展开模式侧边栏扩展 — Phase 4

**Reason**: 展开/紧凑模式切换已移除，侧边栏模型不再适用。导航功能通过 Zone 3 底部导航栏实现。

**Migration**: 移除侧边栏相关 CSS/JS；导航项（对话/成员/任务/技能/设置）重新映射到 Zone 3 底部导航栏（身份识别/任务看板/通知中心/设置）。

### Requirement: 紧凑模式标题栏图标扩展 — Phase 4

**Reason**: 紧凑模式已移除，标题栏图标扩展不再适用。

**Migration**: 任务看板和技能管理的入口通过 Zone 3 底部导航栏访问。

### Requirement: 对话消息气泡

**Reason**: 消息气泡的视觉样式从蓝色/灰色双色方案替换为暖橙色/深色双色方案，并整合到 Chat Overlay 中。气泡形状、尺寸、间距、动画等具体参数变更。

**Migration**: 移除原 `.message.user`、`.message.assistant`、`.message.system` 样式；新气泡样式见新增的 `chat-overlay` 和 `inline-conversation-board` 规格。

### Requirement: 多人模式指示器

**Reason**: 多人模式指示器原位于标题栏状态指示点右侧，标题栏已移除。多人模式状态将整合到 Zone 1 状态栏的硬件芯片区域或 Orb 光球动画中（后续迭代）。

**Migration**: 多人模式相关 DOM 元素和 CSS（红色圆点、排队人数标签、弹出层）暂移除；IPC 事件 `multi-person-status-changed` 保留但不渲染 UI。

### Requirement: 任务看板面板

**Reason**: 原任务看板面板为独立的侧边栏/内容区面板（TaskDashboard），包含完整的筛选、排序、统计、操作按钮等功能。新设计中，任务信息以内联列表形式嵌入 Zone 2 下部（`task-list-panel`），为简化预览视图，不包含筛选/排序/统计/操作按钮等完整功能。完整的任务看板功能通过 Zone 3 导航栏链接至 `tasks.html` 独立页面（后续变更实现）。

**Migration**: 移除原 TaskDashboard 相关的 DOM 元素、CSS 和 IPC 监听；内联任务列表（`.task-list-scroll`）仅展示最近任务的摘要信息（状态图标+标题+来源+耗时），点击后打开 Chat Overlay。

### Requirement: 技能管理面板

**Reason**: 原技能管理面板为独立的侧边栏/内容区面板（SkillManagementPanel），包含卡片网格、详情浮窗、搜索筛选等功能。新设计中技能管理入口通过 Zone 3 导航栏链接至独立页面（后续变更实现）。

**Migration**: 移除原 SkillManagementPanel 相关的 DOM 元素、CSS 和 IPC 监听；Zone 3 导航栏不单独设置技能入口（功能可整合到设置页面或独立页面）。

## ADDED Requirements

### Requirement: 外置窗口控制条

在 phone-frame 容器外部（窗口左上角）SHALL 渲染一个小型半透明控制条，包含最小化和关闭按钮。控制条背景 SHALL 为 `rgba(255,255,255,0.06)`，带毛玻璃效果（`backdrop-filter: blur(12px)`），药丸形（`border-radius: var(--radius-full)`）。按钮样式 SHALL 为无边框透明背景，文字色 `var(--fg-2)`，悬停时变更为 `var(--fg)`。

#### Scenario: 控制条渲染

- **WHEN** 主面板渲染
- **THEN** 窗口左上角显示小型药丸形控制条，包含最小化（─）和关闭（✕）按钮

#### Scenario: 点击关闭按钮最小化至托盘

- **WHEN** 用户点击控制条的关闭按钮
- **THEN** 窗口隐藏，应用在系统托盘继续运行

### Requirement: 返回首页链接

控制条旁 SHALL 显示一个"返回首页"链接（`.back-home`），药丸形，半透明背景 `rgba(255,255,255,0.06)`，毛玻璃效果，文字 `var(--fg-2)`，带左箭头 SVG 图标，字号 `var(--text-sm)`。链接指向 `index.html`。悬停时文字色变更为 `var(--fg)`，背景增强至 `rgba(255,255,255,0.1)`。

#### Scenario: 返回链接渲染

- **WHEN** 主面板渲染
- **THEN** 窗口左上角控制条旁显示"←"返回链接

#### Scenario: 点击返回链接

- **WHEN** 用户点击返回首页链接
- **THEN** 浏览器/Electron 导航至 index.html

### Requirement: 手势浮层保留

原 `gesture-toast`（手势浮层提示）和 `pause-banner`（暂停横幅）SHALL 保留，继续在原位（窗口右下角和面板顶部）渲染，IPC 事件通路不变。

#### Scenario: 举手浮层提示仍能显示

- **WHEN** 渲染器收到 `gesture:detected` 事件，`gesture_type` 为 `"raise_hand"`
- **THEN** 窗口右下角显示浮层 "✋ 举手" 提示，3 秒后淡出

### Requirement: 错误提示保留

原 `error-toast` 错误提示弹窗 SHALL 保留，继续在原位渲染，IPC 事件通路不变。

#### Scenario: 错误提示仍能显示

- **WHEN** 渲染器收到 `error` 事件
- **THEN** 窗口底部显示红色错误提示弹窗，5 秒后自动隐藏
