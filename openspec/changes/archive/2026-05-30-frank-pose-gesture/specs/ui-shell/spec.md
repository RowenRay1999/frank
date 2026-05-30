# ui-shell — Phase 5 手势反馈

## ADDED Requirements

### Requirement: 手势识别浮层提示
Electron 渲染器 SHALL 监听 `gesture.detected` 事件，在窗口右下角显示半透明浮层提示，内容为手势图标和中文名称，3 秒后自动淡出。

#### Scenario: 举手浮层提示
- **WHEN** 渲染器收到 `gesture.detected` 事件，`gesture_type` 为 `"raise_hand"`
- **THEN** 窗口右下角显示浮层 "✋ 举手 — 对话已暂停"，3 秒后 opacity 动画淡出至消失

#### Scenario: 挥手浮层提示
- **WHEN** 渲染器收到 `gesture.detected` 事件，`gesture_type` 为 `"wave"`
- **THEN** 窗口右下角显示浮层 "👋 挥手 — 技能已切换"

#### Scenario: 走近浮层提示
- **WHEN** 渲染器收到 `gesture.detected` 事件，`gesture_type` 为 `"come_closer"`
- **THEN** 窗口右下角显示浮层 "🚶 正在激活..."

#### Scenario: 自定义手势浮层提示
- **WHEN** 渲染器收到 `gesture.detected` 事件，`gesture_type` 为 `"custom"`，包含 `gesture_id`
- **THEN** 窗口右下角显示浮层 "🤌 [自定义手势名称]"

### Requirement: 手势暂停横幅
当 `raise_hand` 手势触发对话暂停时，聊天面板顶部 SHALL 显示暂停状态横幅。

#### Scenario: 显示暂停横幅
- **WHEN** 渲染器收到对话暂停事件
- **THEN** 聊天面板顶部显示黄色横幅："⏸️ 对话已暂停 — 再次举手即可恢复"，并显示暂停时长计时器

#### Scenario: 恢复时隐藏横幅
- **WHEN** 再次收到 `raise_hand` 手势事件（恢复对话）
- **THEN** 暂停横幅消失，聊天面板恢复正常

### Requirement: IPC 手势事件通路
Electron 主进程 SHALL 转发 Python 后端的 `gesture.detected` WebSocket 消息到渲染进程。

#### Scenario: 手势事件 IPC 转发
- **WHEN** 主进程收到 WebSocket 消息 `{ type: "gesture.detected", payload: { gesture_type: "raise_hand", confidence: 0.85 } }`
- **THEN** 主进程通过 `mainWindow.webContents.send('gesture:detected', payload)` 转发到渲染器

#### Scenario: 预加载 API 暴露手势事件
- **WHEN** 渲染器通过 `window.frankAPI` 监听事件
- **THEN** `onGestureDetected` 回调在被调用时传入 `{ gesture_type, confidence, gesture_id, timestamp }`
