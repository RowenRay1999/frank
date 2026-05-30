## ADDED Requirements

### Requirement: 状态栏两行布局

Zone 1（`.zone-status`）SHALL 采用双行纵向布局：
- **上行**（`.status-row-top`）：水平 flex，包含用户身份区块（左侧 `flex: 1`）和右侧状态区块（时间 + 通知预览）
- **下行**（`.status-row-hw`）：水平 flex，包含硬件状态芯片

Zone 1 整体 SHALL 应用毛玻璃效果（`backdrop-filter: blur(20px)`），底部 `1px solid var(--border-soft)` 分隔线。

#### Scenario: 状态栏双行渲染

- **WHEN** 主面板渲染
- **THEN** Zone 1 显示两行：上行为用户头像+名称+角色+时间+通知预览，下行为 CAM/MIC/SCR 硬件芯片

### Requirement: 用户身份展示

上行左侧用户身份区块 SHALL 包含：
- **头像**（`.user-avatar`）：28×28px 圆形，暖橙色半透明背景（`var(--accent-soft)`），1.5px 橙色边框（`var(--accent)`），居中显示用户 display_name 的首字符（font-family: `var(--font-display)`, 13px, weight 600, color `var(--accent)`）
- **名称**（`.user-name`）：11px，weight 600，`var(--fg)` 色
- **角色标签**（`.user-role`）：10px，等宽字体，`var(--muted)` 色，letter-spacing 0.04em

当系统未识别用户身份时，名称 SHALL 显示"访客"，角色标签显示"未识别"，头像显示"?"。

#### Scenario: 已识别用户显示身份

- **WHEN** 系统已确认用户身份（display_name="爸爸"，role="adult"）
- **THEN** Zone 1 上行左侧头像显示"爸"，名称为"爸爸"，角色为"成人"

#### Scenario: 未识别用户显示默认

- **WHEN** 系统未识别任何用户身份
- **THEN** Zone 1 上行左侧头像显示"?"，名称为"访客"，角色为"未识别"

### Requirement: 实时时钟

上行右侧 SHALL 显示一个实时时钟（`.time-block`），格式 "HH:mm"，等宽字体（`var(--font-mono)`），10px，颜色 `var(--fg-2)`，letter-spacing 0.03em。时钟 SHALL 每 10 秒更新一次以确保准确性。

#### Scenario: 时钟显示当前时间

- **WHEN** 当前系统时间为 14:32
- **THEN** Zone 1 上行右侧显示 "14:32"

#### Scenario: 时钟每分钟更新

- **WHEN** 时间从 14:32 变为 14:33
- **THEN** 时钟显示在 10 秒内更新为 "14:33"

### Requirement: 通知预览

上行右侧（时钟旁）SHALL 显示通知预览按钮（`.notif-preview`），包含：
- **通知点**（`.notif-preview-dot`）：6×6px 橙色圆点，带 `0 0 5px var(--accent)` 发光
- **预览文本**（`.notif-preview-text`）：最新通知摘要，10px，`var(--fg-2)`，最大宽度 72px，超出省略
- **通知计数**（`.notif-count`）：未读通知数量，等宽字体，10px，weight 600，`var(--accent)` 色

点击通知预览 SHALL 导航至通知中心页面（`notifications.html`）。悬停时背景色 SHALL 变更为 `var(--surface-elevated)`。

#### Scenario: 有未读通知时显示预览

- **WHEN** 系统有 3 条未读通知，最新一条为"小宝的钢琴课下周时间有变动"
- **THEN** 通知预览显示橙色圆点、截断的预览文本（最多 72px）和数字 "3"

#### Scenario: 无通知时隐藏预览

- **WHEN** 系统无未读通知
- **THEN** 通知预览按钮隐藏

### Requirement: 硬件状态芯片

下行 SHALL 展示 3 个硬件状态芯片（`.hw-chip`），每个包含一个 5×5px 圆点和一个英文标签：
- **CAM**：摄像头状态
- **MIC**：麦克风状态
- **SCR**：屏幕录制状态

芯片 SHALL 为药丸形状（`border-radius: var(--radius-full)`），等宽字体 10px，weight 500，letter-spacing 0.03em，背景 `var(--border-soft)`，文本色 `var(--muted)`。

激活状态（`.hw-chip.active`）下，芯片背景 SHALL 变为 `var(--accent-soft)`，文本色变为 `var(--accent)`，圆点带 `0 0 5px currentColor` 发光。

#### Scenario: 摄像头激活

- **WHEN** 摄像头正在工作（人脸识别中）
- **THEN** CAM 芯片显示 `.active` 样式：橙色背景、橙色文本、圆点发光

#### Scenario: 麦克风待机

- **WHEN** 麦克风处于待机状态
- **THEN** MIC 芯片显示默认样式：灰色背景、灰色文本、圆点无发光

#### Scenario: 屏幕录制未激活

- **WHEN** 屏幕录制功能未开启
- **THEN** SCR 芯片显示默认样式

### Requirement: 状态栏 IPC 联动

Zone 1 的用户身份展示 SHALL 通过 `window.frankAPI.onIdentityConfirmed` 事件更新。硬件芯片状态 SHALL 通过 `window.frankAPI.onStateChanged` 和相应的设备状态事件更新。时钟 SHALL 通过 JavaScript `setInterval` 本地更新。

#### Scenario: 身份确认后更新 Zone 1

- **WHEN** 渲染进程收到 `identity:confirmed` IPC 事件，payload 包含 `display_name: "爸爸"`, `role: "adult"`
- **THEN** Zone 1 用户身份区域更新为显示"爸爸"和"成人"

#### Scenario: 设备状态变更更新芯片

- **WHEN** 摄像头因权限问题不可用
- **THEN** CAM 芯片移除 `.active` 类，恢复灰色默认样式
