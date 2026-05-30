## Why

当前 Frank 桌面应用的界面关闭按钮（✕）和窗口控制完全失效——点击关闭按钮后无任何响应，用户无法通过界面关闭窗口或退出程序。唯一的退出路径是系统托盘的右键菜单中的"退出"选项，这对普通用户来说极其隐蔽且不符合桌面应用的使用习惯。此外，最小化按钮（─）同样无法正常工作。

## What Changes

- **修复关闭按钮**：界面右上角 ✕ 按钮改为将窗口最小化到系统托盘（与现有 `minimize_to_tray` 行为一致）
- **修复最小化按钮**：界面右上角 ─ 按钮改为最小化窗口
- **新增退出入口**：在应用窗口的控制区域增加退出程序的显式入口
- **新增 IPC 通道**：为渲染进程添加 `window:minimize`、`window:hide`、`app:quit` 三条 IPC 通道
- **修复 preload 桥接**：将窗口控制操作从错误的 WebSocket → Python 路径修正为正确的 IPC → Electron 主进程路径

## Capabilities

### New Capabilities
- `app-window-controls`: 应用窗口控制（最小化、关闭到托盘、退出程序）

### Modified Capabilities
<!-- None - this is a new standalone capability -->

## Impact

- **Electron 主进程**：`src/electron/main/ipc.js` — 新增 3 个 IPC handler；`src/electron/main/preload.js` — 新增 3 个 API 暴露方法
- **Electron 渲染进程**：`src/electron/renderer/app.js` — 修改关闭/最小化按钮的事件处理逻辑；`src/electron/renderer/index.html` — 可能在窗口控制区增加退出按钮
- **WebSocket 消息路由**：不再需要将 `window.minimize` / `window.close` 类型消息路由到 Python 后端（这些消息本就不应由 Python 处理）
