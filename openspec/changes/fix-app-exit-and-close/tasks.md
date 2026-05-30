## 1. 主进程 IPC 通道

- [x] 1.1 在 `src/electron/main/ipc.js` 的 `createIPC` 中新增 `frank:minimizeWindow` handler — 调用 `mainWindow.minimize()`
- [x] 1.2 在 `src/electron/main/ipc.js` 的 `createIPC` 中新增 `frank:hideWindow` handler — 调用 `mainWindow.hide()`
- [x] 1.3 在 `src/electron/main/ipc.js` 的 `createIPC` 中新增 `frank:quitApp` handler — 弹出确认对话框，确认后设置 `app.isQuitting = true` 并调用 `app.quit()`

## 2. Preload 桥接层

- [x] 2.1 在 `src/electron/main/preload.js` 中通过 `contextBridge.exposeInMainWorld` 暴露 `minimizeWindow()` — 调用 `ipcRenderer.invoke('frank:minimizeWindow')`
- [x] 2.2 在 `src/electron/main/preload.js` 中暴露 `hideWindow()` — 调用 `ipcRenderer.invoke('frank:hideWindow')`
- [x] 2.3 在 `src/electron/main/preload.js` 中暴露 `quitApp()` — 调用 `ipcRenderer.invoke('frank:quitApp')`

## 3. 渲染进程 UI

- [x] 3.1 修改 `src/electron/renderer/app.js` 中 `btn-minimize` 的事件处理 — 改为调用 `window.frankAPI.minimizeWindow()`
- [x] 3.2 修改 `src/electron/renderer/app.js` 中 `btn-close` 的事件处理 — 改为调用 `window.frankAPI.hideWindow()`
- [x] 3.3 在 `src/electron/renderer/index.html` 的 `.window-controls` 中添加退出按钮（`btn-quit`），使用区分性样式
- [x] 3.4 在 `src/electron/renderer/app.js` 中添加 `btn-quit` 的事件处理 — 调用 `window.frankAPI.quitApp()`
- [x] 3.5 在 `src/electron/renderer/styles.css` 中为退出按钮添加样式（危险色 hover、与关闭按钮间距）

## 4. 验证

- [ ] 4.1 验证 ─ 最小化按钮：点击后窗口正确最小化，可从任务栏恢复
- [ ] 4.2 验证 ✕ 关闭按钮：点击后窗口隐藏到托盘，进程仍在运行
- [ ] 4.3 验证退出按钮：点击后弹出确认对话框，确认后进程完全退出且 Python 子进程终止
- [ ] 4.4 验证退出取消：弹出确认对话框后选择取消，应用继续正常运行
- [ ] 4.5 验证托盘退出：托盘菜单"退出"选项仍正常工作
