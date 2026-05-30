## MODIFIED Requirements

### Requirement: 窗口管理

系统 SHALL 在 Electron 主进程中创建一个无边框窗口（`frame: false`）。

- **默认尺寸**：800×600px
- **最小尺寸**：500×400px
- **可缩放**：`resizable: true`
- **背景色**：`backgroundColor: '#0a0a0c'`
- **初始位置**：居中（首次启动时 `mainWindow.center()`）
- **位置持久化**：窗口位置在会话间持久化

系统 MUST 提供系统托盘图标与右键菜单（显示/隐藏窗口、退出）。点击窗口关闭按钮 SHALL 将应用最小化至托盘。

#### Scenario: 默认启动尺寸为 800×600

- **WHEN** 用户首次启动 Frank
- **THEN** 窗口以 800×600px 呈现，居中于屏幕

#### Scenario: 窗口可缩放

- **WHEN** 用户拖拽窗口任意边缘或角落
- **THEN** 窗口尺寸变化，最小不小于 500×400

#### Scenario: 窗口位置被持久化

- **WHEN** 用户调整窗口位置后关闭并重新启动 Frank
- **THEN** 窗口恢复至上次关闭时的屏幕位置

#### Scenario: 关闭窗口最小化到托盘

- **WHEN** 用户点击窗口控制条的关闭按钮
- **THEN** 窗口隐藏，应用继续在系统托盘运行

### Requirement: 外置窗口控制条

（不变——保留原需求）
在窗口右上角 SHALL 渲染一个小型半透明控制条，包含最小化和关闭按钮。

### Requirement: 返回首页链接

（不变——保留原需求）
控制条旁 SHALL 显示一个"返回首页"链接（`.back-home`）……

## ADDED Requirements

### Requirement: 窗口拖拽区域

Zone 1 状态栏（`.zone-status`）SHALL 设为 `-webkit-app-region: drag` 以支持窗口拖动。Zone 1 内的交互子元素 SHALL 显式设为 `-webkit-app-region: no-drag`。

#### Scenario: 拖拽状态栏移动窗口

- **WHEN** 用户按住 Zone 1 状态栏空白区域并拖拽
- **THEN** 窗口跟随鼠标移动

#### Scenario: 状态栏内按钮不受拖拽影响

- **WHEN** 用户点击 Zone 1 内的通知预览按钮
- **THEN** 点击事件正常触发（打开通知面板），窗口不移动
