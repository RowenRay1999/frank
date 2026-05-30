## Context

Frank 是一个 Electron 桌面应用，采用 **主进程 + 渲染进程** 架构，渲染进程通过 WebSocket 与 Python 推理服务通信。当前窗口控制（最小化、关闭、退出）的实现存在架构层面的错误：

- **渲染进程** (`app.js`) 的关闭/最小化按钮将 `window.close` / `window.minimize` 消息通过 WebSocket 发送到 Python 后端
- **主进程** (`ipc.js`) 从未注册任何窗口控制的 IPC handler
- **preload** (`preload.js`) 暴露的 `sendMessage` API 实际路由到 WebSocket → Python，而非 IPC → Electron 主进程
- 唯一真实的退出路径是托盘菜单的"退出"选项

这是一个架构级 bug：窗口控制逻辑被错误地路由到了 Python 推理服务，而正确的目标应该是 Electron 主进程。

## Goals / Non-Goals

**Goals:**
- 修复界面最小化按钮（─），使其正确最小化 Electron 窗口
- 修复界面关闭按钮（✕），使其将窗口隐藏到系统托盘（符合 `minimize_to_tray` 配置）
- 在窗口控制区新增退出按钮，提供显式的退出入口
- 为渲染进程提供正确的 IPC 通道来执行窗口操作
- 保持现有托盘"退出"菜单功能不变

**Non-Goals:**
- 不改变 `minimize_to_tray` 配置的语义
- 不修改 Python 后端的任何代码
- 不修改系统托盘的行为或菜单结构
- 不改变 `app.on('window-all-closed')` 的行为（保持不退出，仅隐藏到托盘）

## Decisions

### 1. 窗口控制使用 IPC 而非 WebSocket

**选择**：新增 `frank:minimizeWindow`、`frank:hideWindow`、`frank:quitApp` 三条 IPC 通道。

**替代方案**：继续走 WebSocket → Python 路径，在 Python 端通过某种机制回调 Electron？—— 这引入了不必要的复杂性、延迟和故障点。窗口操作是纯前端行为，应由 Electron 主进程直接处理。

**理由**：IPC 是 Electron 主进程和渲染进程之间的标准通信机制，零延迟、无外部依赖。

### 2. 关闭按钮行为：隐藏到托盘，而非真正关闭窗口

**选择**：✕ 按钮调用 `mainWindow.hide()`，关闭效果等同于最小化到托盘。

**替代方案**：✕ 按钮直接调用 `app.quit()` —— 这会破坏 `minimize_to_tray` 的语义，与托盘"退出"功能重复。

**理由**：与现有的 `mainWindow.on('close')` 拦截逻辑一致，保持 macOS/Windows 托盘应用的标准行为。

### 3. 退出按钮位置：窗口控制条内

**选择**：在 HTML 的 `.window-controls` 区域内增加一个退出按钮（使用更明显的图标或样式区分），点击后弹出确认对话框，确认后退出。

**替代方案**：
- 在设置页面添加退出选项 —— 操作路径太深
- 仅依赖托盘菜单退出 —— 当前问题所在

**理由**：窗口控制条是用户关闭窗口时的自然视线区域，在此处增加退出入口符合用户直觉。

### 4. IPC handler 实现位置

**选择**：在 `ipc.js` 的 `createIPC` 函数中新增 handler，直接操作传入的 `mainWindow` 引用和 `app` 模块。

**理由**：`ipc.js` 已有 `createIPC` 的模式，且 `mainWindow` 已在 `main.js` 创建时传入。保持 IPC 逻辑集中。

## Risks / Trade-offs

- **[风险] 退出确认对话框可能打断用户流程** → 使用简单的确认对话框（`dialog.showMessageBox`），仅在点击退出按钮时触发，不影响托盘退出流程
- **[风险] 新增退出按钮可能被误触** → 使用不同样式（红色/危险色），与关闭按钮保持间距，并加入确认对话框
- **[权衡] 在最小化到托盘的语义下，「退出」和「关闭到托盘」是两个独立操作** → 这是设计选择：关闭到托盘保持后台运行，退出彻底终止进程

## Open Questions

<!-- 无待解决问题 -->
