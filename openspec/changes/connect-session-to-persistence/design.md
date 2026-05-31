## Context

当前会话 UI（convo-section、convo-bubbles、chatOverlay）为纯静态 HTML 占位，`app.js` 的 `sendMessage()` 只创建 DOM 节点不作持久化。后端 `ConversationOrchestrator` 负责实时对话流转（STT→LLM→TTS），通过 `on_user_message` / `on_assistant_message` 回调广播 WebSocket 事件，但消息不落库。现有 SQLite 数据库（`data/frank.db`，schema v2）存储成员、生物特征、手势等，没有会话/消息相关表。

前端 UI 框架为 viteless vanilla JS（`app.js` + `index.html` + `styles.css`），与后端通过 `window.frankAPI.sendMessage()` 进行 IPC，后端通过 WebSocket 推送事件。所有交互遵循 `Message` 信封格式（type/id/timestamp/payload）。

**约束**：所有数据必须本地存储（隐私设计原则），不引入新进程或外部数据库。前端保持 viteless 架构。

## Goals / Non-Goals

**Goals：**
- 数据库增加 sessions 和 messages 表，支持会话的创建、列表查询和消息的追加、历史加载
- 后端对话编排器自动将每条用户消息和助手回复持久化到当前会话
- 前端启动时自动加载最近会话的消息历史并渲染到 convo-bubbles 和 chatMessages
- 前端 `sendMessage()` 将手动输入发往后端处理，消息经 IPC→WebSocket→LLM→持久化→广播→UI 更新形成闭环
- 前端监听 `chat.user_message` / `chat.assistant_message` 事件实时追加消息到 UI
- 支持会话列表查询和切换（chatOverlay 内切换历史会话）

**Non-Goals：**
- 不实现消息搜索（超出当前范围）
- 不实现消息编辑/删除（本次只做基础 CRUD）
- 不实现导出/导入功能
- 不修改 LLM 推理逻辑（只改持久化层）
- 不引入向量数据库或外部存储

## Decisions

### D1：会话粒度 — 每个启动周期一个会话 vs 按成员/时间切分

**选择**：按启动周期自动创建会话 + 支持手动创建。

每个会话记录 `started_at` / `last_active_at` / `member_id`（可选关联已识别成员）。新会话在以下时机自动创建：① 服务启动时（若不存在活跃会话）；② 成员身份切换时（从"访客"识别为"主人/成人/儿童"）。前端支持在 chatOverlay 顶部切换历史会话。

**理由**：自然对应真实使用场景——用户每次打开 Frank 开始一轮对话。按启动周期切分避免单个会话无限膨胀。成员切换时重新创建会话保持上下文隔离。

**替代方案**：按固定条数/时间窗口切分 → 过于机械，不如按生命周期自然切分直观。

### D2：消息持久化时机 — 同步写 vs 异步写 vs 批量写

**选择**：在 `on_user_message` 和 `on_assistant_message` 回调中同步写入数据库。

`ConversationOrchestrator` 现有回调即用即写，使用 `threading.Lock` 保护的 SQLite WAL 模式连接，写入开销 <1ms 不影响对话实时性。每条消息独立写入，崩溃时最多丢失当前正在生成的消息。

**理由**：代码侵入最小（直接复用现有回调），单条同步写延迟可忽略（SQLite WAL + 本地存储），不需要额外的写缓冲队列。

**替代方案**：异步队列批量写 → 增加了复杂度（需要队列管理、flush 策略）而收益不大；异步写崩溃时可能丢失未 flush 的消息。

### D3：数据库表结构

**选择**：在现有 SQLite 数据库中新增两张表，schema 升级至 v3。

```sql
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,           -- UUID
    member_id TEXT,                -- 关联成员（可空，表示未识别访客）
    created_at TEXT NOT NULL,      -- ISO8601
    last_active_at TEXT NOT NULL,  -- ISO8601
    is_active INTEGER DEFAULT 1,  -- 是否活跃（同一时间仅一个活跃）
    message_count INTEGER DEFAULT 0
);

CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    role TEXT NOT NULL CHECK(role IN ('user','assistant','system')),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,      -- ISO8601
    metadata TEXT DEFAULT '{}'     -- JSON，预留扩展（如 TTS 耗时、LLM model 等）
);

CREATE INDEX idx_messages_session ON messages(session_id, created_at);
CREATE INDEX idx_sessions_active ON sessions(is_active) WHERE is_active = 1;
```

**理由**：messages 的 `id` 使用 INTEGER 自增（session_id + id 组合有序，天然支持按时间分页）。`metadata` 为 TEXT JSON 预留扩展而不膨胀字段。`is_active` 用于快速定位当前活跃会话。

### D4：前端数据流

**选择**：前端在 `DOMContentLoaded` 后发送 `session.list` 获取会话列表，选取最新活跃会话后发送 `session.messages` 加载消息历史并渲染。后续消息通过 WebSocket `chat.user_message` / `chat.assistant_message` 事件实时推送追加。

前端维护状态对象：
```js
const sessionState = {
  sessions: [],          // 会话列表
  currentSessionId: null,
  messages: [],          // 当前会话消息
};
```

`sendMessage()` 改为通过 `window.frankAPI.sendMessage({ type: 'chat.text_input', payload: { text } })` 发送给后端（由 ConversationOrchestrator 的 `handle_text_input` 处理），不复用本地 DOM 伪造。

**理由**：所有消息经过后端统一处理，确保 LLM 回复也被持久化并广播，前端只负责渲染。

### D5：convo-bubbles 预览区域策略

**选择**：convo-bubbles（导航栏下方的会话预览区）始终显示当前活跃会话的最后 3-5 条消息摘要，实时更新。新消息到达时滚动到底部。点击"展开"按钮打开 chatOverlay 查看完整历史。

**理由**：预览区应快速提供上下文概览，不做完整滚动。chatOverlay 负责完整对话面板。

## Risks / Trade-offs

- **并发写入冲突**：如果多个 WebSocket 连接同时写入 → SQLite WAL 模式下写操作串行化由 SQLite 内部锁处理，实际场景中仅一个 Electron 客户端连接，风险可控
- **会话膨胀**：长时间运行后 sessions 表可能积累大量数据 → 后续可增加自动清理策略（保留最近 N 个会话），当前版本 `message_count` 字段已为清理提供依据
- **消息丢失窗口**：消息先发出再写入数据库，若进程在写 DB 前崩溃 → 该条消息丢失。与现有架构一致（当前消息也不持久化），这是纯增益改动，不引入新的风险类别
- **schema 迁移**：从 v2→v3 需要 ALTER TABLE 或 CREATE TABLE IF NOT EXISTS → 使用 `init_database()` 中已有的版本检查机制，增量建表，无破坏性变更

## Migration Plan

1. 部署新代码后首次启动，`init_database()` 检测到 `SCHEMA_VERSION = 3` > 当前版本，自动执行 `CREATE TABLE IF NOT EXISTS sessions/messages` 和索引创建
2. 无需数据迁移（全新表，无现有数据需要转换）
3. 回滚：删除 `sessions` 和 `messages` 表，将 `SCHEMA_VERSION` 调回 2。不影响已有功能
4. 前端无 breaking change：现有占位 UI 元素保留，数据加载后自动填充

## Open Questions

- 是否需要支持按日期分组显示会话（如"今天""昨天""更早"）？→ 建议后续迭代
- convo-bubbles 预览区在未连接后端时的降级展示策略？→ 保持当前静态占位文案
