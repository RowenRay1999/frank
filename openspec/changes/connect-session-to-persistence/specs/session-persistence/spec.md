# session-persistence — 会话持久化

## 概述

为 Frank 系统新增会话持久化能力，使对话消息在 SQLite 数据库中持久存储，前端会话 UI 连接到真实数据源。涵盖会话生命周期管理、消息持久化、历史加载、前端数据绑定四个维度。

---

## ADDED Requirements

### Requirement: 数据库会话与消息表结构

系统 SHALL 在现有 SQLite 数据库（`data/frank.db`）中新增 `sessions` 和 `messages` 两张表，schema 版本号升级至 3。`sessions` 表 MUST 包含字段：`id`（TEXT PRIMARY KEY，UUID）、`member_id`（TEXT 可空，关联 members 表）、`created_at`（TEXT NOT NULL，ISO8601）、`last_active_at`（TEXT NOT NULL，ISO8601）、`is_active`（INTEGER DEFAULT 1）、`message_count`（INTEGER DEFAULT 0）。`messages` 表 MUST 包含字段：`id`（INTEGER PRIMARY KEY AUTOINCREMENT）、`session_id`（TEXT NOT NULL REFERENCES sessions(id)）、`role`（TEXT NOT NULL CHECK IN user/assistant/system）、`content`（TEXT NOT NULL）、`created_at`（TEXT NOT NULL，ISO8601）、`metadata`（TEXT DEFAULT '{}'，JSON 字符串）。系统 MUST 在 `messages(session_id, created_at)` 和 `sessions(is_active) WHERE is_active=1` 上建立索引。

#### Scenario: 升级时自动建表
- **WHEN** 系统首次以 schema v3 启动，检测到当前 schema 版本低于 3
- **THEN** `init_database()` 自动执行 `CREATE TABLE IF NOT EXISTS sessions` 和 `CREATE TABLE IF NOT EXISTS messages`，并插入 `schema_version` 记录为 3；已有表和数据不受影响

#### Scenario: 后续启动不再重复建表
- **WHEN** 系统再次启动且 schema 版本已为 3
- **THEN** 不再执行建表 DDL

---

### Requirement: 会话自动创建

系统 SHALL 在以下时机自动创建新会话：① 服务启动时若不存在 `is_active=1` 的会话，则创建新会话；② 当前活跃会话的成员身份从"未识别"变为"已识别"（如访客被识别为主人）时，将旧会话 `is_active` 设为 0 并创建新会话。新会话 MUST 获得 UUID `id`，`created_at` 和 `last_active_at` 设为当前时间，`is_active` 设为 1。

#### Scenario: 服务启动时无活跃会话
- **WHEN** Python 服务启动完成，`init_database()` 和模块初始化已执行，查询 `sessions` 表中无 `is_active=1` 的记录
- **THEN** 系统自动创建一条新会话记录，`is_active=1`，`member_id` 为 NULL（表示未识别访客）

#### Scenario: 服务启动时已有活跃会话
- **WHEN** Python 服务启动完成，查询 `sessions` 表中已存在 `is_active=1` 的记录
- **THEN** 系统复用该活跃会话，不创建新会话

#### Scenario: 成员身份从访客变为已识别
- **WHEN** 身份融合引擎检测到当前用户从未识别状态变为已识别成员（如 face_embedding 匹配到已知成员），且当前活跃会话的 `member_id` 为 NULL
- **THEN** 系统将当前会话 `is_active` 设为 0，创建新会话并将 `member_id` 设为识别到的成员 ID

---

### Requirement: 消息持久化

系统 SHALL 在每次对话交互中将用户消息和助手回复持久化到当前活跃会话的 `messages` 表中。持久化 MUST 通过 `ConversationOrchestrator` 的 `on_user_message` 和 `on_assistant_message` 回调触发，写入操作为同步执行。每条消息 MUST 记录 `session_id`（当前活跃会话 ID）、`role`（user 或 assistant）、`content`（消息文本）、`created_at`（当前 ISO8601 时间戳）。写入成功后 MUST 更新对应 `sessions` 记录的 `last_active_at` 和 `message_count`（递增 1）。

#### Scenario: 用户语音消息被持久化
- **WHEN** `ConversationOrchestrator.process_speech()` 完成 STT 转写并调用 `on_user_message` 回调
- **THEN** 系统将转写文本以 `role='user'` 写入当前活跃会话的 `messages` 表

#### Scenario: 助手 LLM 回复被持久化
- **WHEN** `ConversationOrchestrator.process_speech()` 完成 LLM 推理并调用 `on_assistant_message` 回调
- **THEN** 系统将 LLM 回复文本以 `role='assistant'` 写入当前活跃会话的 `messages` 表

#### Scenario: 手动文字输入被持久化
- **WHEN** 前端通过 `chat.text_input` 消息类型发送文字，后端 `ConversationOrchestrator.handle_text_input()` 被调用
- **THEN** 系统将用户文字以 `role='user'` 写入，LLM 回复以 `role='assistant'` 写入

#### Scenario: 写入失败不阻塞对话流程
- **WHEN** 消息持久化写入数据库时发生异常（如磁盘满）
- **THEN** 系统记录错误日志，对话流程继续执行（LLM 推理和 TTS 朗读不受影响）

---

### Requirement: 会话列表查询

系统 SHALL 提供 `session.list` IPC 消息处理，返回所有会话的列表，按 `last_active_at` 降序排列。每条会话记录 MUST 包含：`id`、`member_id`、`created_at`、`last_active_at`、`is_active`、`message_count`。若会话关联了成员（`member_id` 非空），MUST 额外返回 `member_display_name` 和 `member_role`。

#### Scenario: 查询会话列表
- **WHEN** 前端发送 `{ type: "session.list" }` 消息
- **THEN** 后端返回 `{ type: "session.list", payload: { sessions: [...] } }`，sessions 数组按 `last_active_at` 降序排列

#### Scenario: 无会话记录
- **WHEN** 前端发送 `session.list` 但数据库中没有会话记录
- **THEN** 后端返回 `{ type: "session.list", payload: { sessions: [] } }`，不返回错误

---

### Requirement: 会话消息历史加载

系统 SHALL 提供 `session.messages` IPC 消息处理，接受 `session_id` 参数，返回该会话的全部消息按 `created_at` 升序排列。每条消息 MUST 包含：`id`、`session_id`、`role`、`content`、`created_at`。支持可选 `limit` 和 `offset` 参数用于分页加载。

#### Scenario: 加载指定会话的全部消息
- **WHEN** 前端发送 `{ type: "session.messages", payload: { session_id: "xxx" } }` 消息
- **THEN** 后端返回 `{ type: "session.messages", payload: { session_id: "xxx", messages: [...] } }`，messages 按 `created_at` 升序排列

#### Scenario: 加载消息带分页
- **WHEN** 前端发送 `{ type: "session.messages", payload: { session_id: "xxx", limit: 20, offset: 0 } }`
- **THEN** 后端返回最多 20 条消息及 `total` 总数，用于前端分页

#### Scenario: 会话不存在
- **WHEN** 前端请求的 `session_id` 在数据库中不存在
- **THEN** 后端返回 `{ type: "session.messages", payload: { session_id: "xxx", messages: [], total: 0 } }`，不返回错误

---

### Requirement: 会话创建

系统 SHALL 提供 `session.create` IPC 消息处理，支持前端手动创建新会话。新会话 MUST 将当前活跃会话 `is_active` 设为 0，然后创建新会话记录。可选 `member_id` 参数指定关联成员。

#### Scenario: 前端手动创建新会话
- **WHEN** 前端发送 `{ type: "session.create", payload: {} }` 消息
- **THEN** 后端将当前活跃会话 `is_active` 设为 0，创建新会话并返回 `{ type: "session.created", payload: { session: { id, created_at, ... } } }`

#### Scenario: 创建会话时指定成员
- **WHEN** 前端发送 `{ type: "session.create", payload: { member_id: "xxx" } }`
- **THEN** 新会话的 `member_id` 设为指定值

---

### Requirement: 前端会话数据绑定

前端 SHALL 在页面加载完成后自动从后端拉取会话列表和当前活跃会话的消息历史，并渲染到对应 UI 区域。`convo-bubbles` 区域 MUST 显示当前活跃会话最近的消息预览（最多 5 条）。`chatMessages` 区域（chatOverlay 内）MUST 在面板打开时显示当前活跃会话的完整消息历史。前端 MUST 监听 WebSocket `chat.user_message` 和 `chat.assistant_message` 事件，实时追加新消息到两个 UI 区域。前端 MUST 监听 `session.created` 事件以更新会话列表。

#### Scenario: 页面加载时渲染会话数据
- **WHEN** 前端 `DOMContentLoaded` 触发且 WebSocket 握手完成
- **THEN** 前端发送 `session.list` 获取会话列表，选取最新活跃会话后发送 `session.messages` 加载消息历史，将消息渲染到 `convoBubbles`（最新 5 条）和 `chatMessages` 区域

#### Scenario: 无历史会话时显示占位提示
- **WHEN** 前端加载会话列表返回空数组或当前会话无消息
- **THEN** `convoTopic` 显示"暂无对话"，`convoMeta` 显示"开始与 Frank 对话吧"，与当前静态占位行为一致

#### Scenario: chat.user_message 事件追加用户消息
- **WHEN** 前端收到 `{ type: "chat.user_message", payload: { text: "..." } }` 事件
- **THEN** 前端在 `convoBubbles` 和 `chatMessages` 中追加一条用户消息气泡，更新 `convoTopic`（显示最新消息摘要）和 `convoMeta`（更新消息计数和时间）

#### Scenario: chat.assistant_message 事件追加助手回复
- **WHEN** 前端收到 `{ type: "chat.assistant_message", payload: { text: "..." } }` 事件
- **THEN** 前端在 `convoBubbles` 和 `chatMessages` 中追加一条助手消息气泡，更新 `convoTopic` 和 `convoMeta`

#### Scenario: 手动输入发送消息
- **WHEN** 用户在 chatInput 输入文字并点击发送或按 Enter
- **THEN** 前端通过 `window.frankAPI.sendMessage({ type: 'chat.text_input', payload: { text } })` 将消息发送给后端处理，不再仅创建本地 DOM 节点

---

### Requirement: 会话切换

用户 SHALL 能够在 chatOverlay 对话面板中查看和切换到历史会话。chatOverlay 顶部 MUST 显示会话列表下拉或横向滚动条，列出所有会话（按时间倒序，标注日期和消息数）。选择某个会话后，前端 MUST 发送 `session.messages` 加载该会话的消息历史并替换 `chatMessages` 内容。

#### Scenario: 切换到历史会话
- **WHEN** 用户在 chatOverlay 顶部选择某个历史会话
- **THEN** `chatMessages` 清空并重新渲染为该会话的消息历史；`convoBubbles` 预览区保持不变（始终显示当前活跃会话的预览）

#### Scenario: 回到当前活跃会话
- **WHEN** 用户正在查看历史会话，点击"回到当前对话"按钮
- **THEN** `chatMessages` 切换回当前活跃会话的消息内容

---

### Requirement: WebSocket 事件广播

系统 SHALL 在创建新会话时通过 WebSocket 广播 `session.created` 事件，通知前端更新会话列表。事件 payload MUST 包含新会话的完整信息（id、member_id、created_at 等）。

#### Scenario: 自动创建会话时广播事件
- **WHEN** 系统因成员身份切换自动创建新会话
- **THEN** 通过 WebSocket 广播 `{ type: "session.created", payload: { session: {...} } }` 给所有连接的客户端
