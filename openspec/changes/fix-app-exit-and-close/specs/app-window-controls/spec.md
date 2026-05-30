## ADDED Requirements

### Requirement: 窗口最小化
系统 SHALL 允许用户通过界面按钮最小化主窗口。

#### Scenario: 点击最小化按钮
- **WHEN** 用户点击窗口控制栏中的最小化按钮（─）
- **THEN** Electron 主窗口 SHALL 执行最小化操作（`mainWindow.minimize()`）

### Requirement: 窗口关闭到系统托盘
系统 SHALL 允许用户通过界面按钮将窗口隐藏到系统托盘（关闭到托盘）。

#### Scenario: 点击关闭按钮
- **WHEN** 用户点击窗口控制栏中的关闭按钮（✕）
- **THEN** Electron 主窗口 SHALL 隐藏（`mainWindow.hide()`），应用继续在系统托盘运行

### Requirement: 退出应用程序
系统 SHALL 提供显式的退出入口，允许用户彻底终止应用程序进程。

#### Scenario: 点击退出按钮并确认
- **WHEN** 用户点击窗口控制栏中的退出按钮
- **THEN** 系统 SHALL 弹出确认对话框询问是否退出
- **AND** 当用户确认后，应用 SHALL 设置退出标志并终止所有进程（Python 子进程、WebSocket 连接、托盘图标）

#### Scenario: 取消退出操作
- **WHEN** 用户点击退出按钮后弹出确认对话框
- **AND** 用户选择取消
- **THEN** 确认对话框关闭，应用继续正常运行

### Requirement: 窗口控制的 IPC 通道
系统 SHALL 为渲染进程提供安全的 IPC 通道来执行窗口操作，不经过 WebSocket/Python 后端。

#### Scenario: 渲染进程请求最小化窗口
- **WHEN** 渲染进程通过 `window.frankAPI.minimizeWindow()` 发起请求
- **THEN** 主进程 SHALL 通过 IPC handler 接收请求并执行窗口最小化

#### Scenario: 渲染进程请求隐藏窗口到托盘
- **WHEN** 渲染进程通过 `window.frankAPI.hideWindow()` 发起请求
- **THEN** 主进程 SHALL 通过 IPC handler 接收请求并执行窗口隐藏

#### Scenario: 渲染进程请求退出应用
- **WHEN** 渲染进程通过 `window.frankAPI.quitApp()` 发起请求
- **THEN** 主进程 SHALL 通过 IPC handler 接收请求，弹出确认对话框，确认后退出应用
