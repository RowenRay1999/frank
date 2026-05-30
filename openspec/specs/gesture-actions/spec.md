# gesture-actions — 手势动作槽

## ADDED Requirements

### Requirement: 手势动作槽注册
系统 SHALL 提供 pub-sub 模式的手势动作槽系统，允许系统模块注册对特定手势的回调。每个手势类型 SHALL 支持多个订阅者。

#### Scenario: 注册举手动作槽
- **WHEN** 对话编排器调用 `pose_module.register_action_slot("raise_hand", pause_conversation_callback)`
- **THEN** 回调被添加到 `raise_hand` 的订阅者列表中

#### Scenario: 同一手势多订阅者
- **WHEN** 两个不同模块（对话和音频）都注册了 `wave` 手势的回调
- **THEN** 两个回调均被存储，触发时按注册顺序依次调用

### Requirement: 手势触发分发
系统 SHALL 在识别到手势时，将 GestureEvent 分发给该手势类型的所有已注册回调。分发 SHALL 在 asyncio 事件循环中异步执行。

#### Scenario: 举手触发暂停对话
- **WHEN** 系统检测到 `raise_hand` 手势（confidence >= 0.7）
- **AND** 对话编排器已注册 `raise_hand` → `pause_conversation` 回调
- **THEN** 系统调用 `pause_conversation` 回调，传入 GestureEvent

#### Scenario: 挥手触发切换技能
- **WHEN** 系统检测到 `wave` 手势
- **AND** 技能加载器已注册 `wave` → `next_skill` 回调
- **THEN** 当前活跃技能切换到下一个可用技能

#### Scenario: 手势事件广播到 Electron
- **WHEN** 任何手势被识别
- **THEN** 系统通过 WebSocket 推送 `gesture.detected` 事件到 Electron 前端，payload 包含 `{ gesture_type, confidence, gesture_id, timestamp }`

### Requirement: 默认手势动作绑定
系统 SHALL 在启动时注册以下默认手势动作绑定：

| 手势 | 动作 | 行为 |
|------|------|------|
| raise_hand | 暂停/恢复对话 | 切换 Chat 状态下的对话暂停 |
| wave | 切换技能 | 循环切换到下一个启用的技能 |
| point | 当前上下文查询 | 指向方向 + 当前对话上下文 → LLM 追问 |
| come_closer | 激活助手 | 从 Idle/Aware 直接进入 Auth，无需唤醒词 |

#### Scenario: 走近自动激活
- **WHEN** 系统处于 Idle 状态，检测到 `come_closer` 手势（用户走近摄像头）
- **THEN** 系统直接转换到 Aware 状态并开始身份融合，无需等待人脸持续检测

#### Scenario: 举手暂停对话
- **WHEN** 系统处于 Chat 状态，检测到 `raise_hand` 手势
- **THEN** LLM 当前输出被暂停，TTS 播放停止，对话进入暂停状态；再次举手恢复对话

### Requirement: 自定义手势动作绑定
系统 SHALL 允许用户将自定义手势绑定到特定动作或快捷指令。绑定 SHALL 通过消息 `gesture.bind` 命令执行，存储在数据库 `gesture_actions` 表中。

#### Scenario: 绑定自定义手势到快捷指令
- **WHEN** 用户发送 `gesture.bind` 命令，指定 `gesture_id: "custom_001"`, `action: "execute_skill"`, `params: {skill_name: "weather"}`
- **THEN** 绑定被存储，后续识别到该自定义手势时自动执行天气查询技能

#### Scenario: 解绑自定义手势
- **WHEN** 用户发送 `gesture.unbind` 命令，指定 `gesture_id: "custom_001"`
- **THEN** 该手势的所有动作绑定被移除

#### Scenario: 查看已绑定的手势
- **WHEN** 用户发送 `gesture.list_bindings` 命令
- **THEN** 返回所有手势动作绑定列表，格式 `[{ gesture_type, gesture_id, action, params }]`

### Requirement: 手势 UI 反馈
系统 SHALL 在 Electron 渲染器中提供手势识别反馈。当手势被识别时，在 UI 中显示半透明浮层动画提示。

#### Scenario: 手势识别浮层
- **WHEN** Electron 收到 `gesture.detected` 事件
- **THEN** 渲染器在窗口右下角显示半透明浮层，显示手势图标和名称，3 秒后自动淡出

#### Scenario: 举手暂停反馈
- **WHEN** `raise_hand` 手势触发对话暂停
- **THEN** 聊天面板顶部显示暂停横幅 "⏸️ 对话已暂停 — 再次举手恢复"，并显示暂停时长计时器

#### Scenario: 走近激活反馈
- **WHEN** `come_closer` 手势触发系统激活
- **THEN** 状态指示器切换为蓝色脉冲，欢迎卡片显示 "👋 你好！我在听"

### Requirement: 手势数据持久化
系统 SHALL 在 SQLite 数据库中新增 `custom_gestures` 和 `gesture_actions` 两张表，存储用户注册的自定义手势和手势动作绑定。

#### Scenario: 跨会话保持自定义手势
- **WHEN** 用户注册自定义手势后重启 Frank
- **THEN** 已注册的自定义手势仍可被识别和匹配

#### Scenario: 数据库 Schema 迁移
- **WHEN** 系统从 schema_version 1 升级到 2
- **THEN** 自动创建 `custom_gestures` 和 `gesture_actions` 表，不影响现有数据
