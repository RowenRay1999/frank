## Why

当前界面上的会话区域（convo-section 会话预览条、convo-bubbles 会话气泡、chatOverlay 对话叠加层）全部为静态占位 UI，发送的消息只创建 DOM 节点随即丢失，刷新后会话记录归零。后端对话编排器（ConversationOrchestrator）在处理 STT→LLM→TTS 流程时也未持久化任何消息。作为一个以对话为核心的 AI 助手，缺乏会话持久化意味着用户无法回顾历史对话、无法跨重启恢复上下文、也无法让 LLM 基于历史消息给出连续回复。现在前端 UI 框架 v3 已稳定，后端消息路由完整，正是打通"前端会话 UI ↔ 持久化数据"这一关键链路的合适时机。

## What Changes

- 数据库新增 `sessions`（会话）与 `messages`（消息）两张表，存储会话元数据、对话消息及其角色/时间戳
- 后端新增会话持久化模块（`session_store.py`），提供会话创建、消息追加、历史查询、会话列表等原子操作
- 后端在对话编排器中集成持久化：`on_user_message` 和 `on_assistant_message` 回调自动将消息写入数据库
- 后端新增 IPC 消息处理器：`session.list`（获取会话列表）、`session.messages`（加载某会话的全部消息）、`session.create`（创建新会话）
- 前端 `app.js` 连接真实数据源：启动时从后端拉取会话列表和最新会话消息，渲染到 convo-bubbles 和 chatMessages
- 前端 `sendMessage()` 将消息通过 WebSocket 发送给后端处理并通过 chatOverlay 展示真实对话
- 前端 chatOverlay 对话面板支持消息滚动加载、会话切换
- 前端接收 `chat.user_message` / `chat.assistant_message` 事件，实时更新会话 UI

## Capabilities

### New Capabilities
- `session-persistence`: 会话数据持久化存储与查询，包括会话列表、消息历史、会话创建，前端 UI 连接到真实持久化数据

### Modified Capabilities
<!-- No existing specs change requirements. This is a new capability that integrates with existing process-communication (IPC/WebSocket) and LLM integration but doesn't modify their spec-level requirements. -->

## Impact

- **数据库**: `data/frank.db` 新增 `sessions` 和 `messages` 两张表（schema v3 迁移）
- **后端**: 新增 `src/python/modules/session/session_store.py`；修改 `src/python/server/main.py` 增加 message handlers；修改 `src/python/shared/database.py` 增加建表与迁移逻辑
- **前端**: 修改 `src/electron/renderer/app.js`（会话 UI 数据连接、WebSocket 事件监听）；修改 `src/electron/renderer/index.html`（如需会话切换 UI 元素）
- **依赖**: 无新增外部依赖
- **IPC 协议**: 新增 `session.list` / `session.messages` / `session.create` 消息类型
