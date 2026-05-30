# 任务管理（Task Management）

## 概述

任务管理系统为多技能协作场景提供异步任务编排能力。LLM 输出指令后，系统根据任务类型决定是同步返回还是进入任务队列，并在整个生命周期内提供状态追踪、异常处理、持久化与通知能力。

## ## ADDED Requirements

### 1. 指令分类（Command Classification）

LLM 输出指令时，需同时产出以下元数据：

| 字段 | 类型 | 说明 |
|------|------|------|
| `task_type` | `"immediate"` \| `"managed"` | 即时任务直接返回结果；托管任务进入队列 |
| `estimated_duration` | `number`（秒） | LLM 预估的执行时长，用于队列调度与超时判定 |

- **Immediate 任务**：系统直接执行并将结果返回给调用方，不走队列。
- **Managed 任务**：系统分配唯一 `task_id`（UUIDv4），将任务插入队列后立即返回 `task_id` 给调用方。
- 分类逻辑由 LLM 在输出中决定，系统层不做二次推断。

### 2. 任务生命周期（Task Lifecycle）

每个任务经历以下状态流转：

```
Submit → Queued → Executing → Completed
                         ↕
                       Failed
```

| 状态 | 说明 |
|------|------|
| `Submitted` | 任务已创建并写入数据库，尚未进入调度 |
| `Queued` | 任务已进入 FIFO 队列，等待执行 |
| `Executing` | 任务正在被 Worker 消费 |
| `Completed` | 任务成功执行完毕 |
| `Failed` | 任务执行失败（含重试用尽后的最终失败） |

- 任何时刻均可通过 `task_id` 查询任务当前状态、进度百分比及结果/错误信息。
- 查询接口：`GET /tasks/:task_id` 或对应内部函数。

### 3. 任务队列（Task Queue）

- **同一用户 FIFO**：同一用户的托管任务按提交顺序串行执行。
- **不同用户并行**：不同用户的任务可同时执行，互不阻塞。
- 每个任务携带 `user_context`（用户 ID、角色、权限等级），供 Worker 在执行时按需使用。
- 队列后端建议使用内存通道 + SQLite 持久化兜底，避免引入外部依赖（如 Redis）。

### 4. 三级异常处理（Three-Level Exception Handling）

| 级别 | 名称 | 行为 |
|------|------|------|
| 🟡 **Yellow** | 可重试异常 | 自动重试最多 3 次，采用指数退避（1s → 2s → 4s）。重试成功则继续，3 次均失败则升级为 Orange。 |
| 🟠 **Orange** | 需关注异常 | 暂停当前任务，通过通知渠道告知用户并提供可选操作：重试、跳过、取消。用户响应前任务保持 Paused 状态。 |
| 🔴 **Red** | 不可恢复异常 | 立即标记为 Failed。通知用户失败原因 + 改进建议，不重试。 |

- 异常分级由任务执行器根据异常类型或异常内容关键字判定。
- 系统提供默认分级规则，技能开发者也可通过配置自定义规则。

### 5. 任务持久化（Task Persistence）

- 使用 **SQLite** 存储任务数据。
- 表结构 `tasks`：

```sql
CREATE TABLE tasks (
    task_id          TEXT PRIMARY KEY,
    user_id          TEXT NOT NULL,
    user_role        TEXT,
    task_type        TEXT NOT NULL,         -- 'immediate' | 'managed'
    status           TEXT NOT NULL DEFAULT 'submitted',
    payload          TEXT,                   -- 原始指令 / 输入数据
    result           TEXT,                   -- 执行结果（JSON）
    error            TEXT,                   -- 错误信息
    progress         INTEGER DEFAULT 0,      -- 0-100
    exception_level  TEXT,                   -- 'yellow' | 'orange' | 'red'
    retry_count      INTEGER DEFAULT 0,
    created_at       TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at       TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at     TEXT
);
```

- 应用重启后自动扫描 `tasks` 表中状态为 `Queued` / `Executing` 的不完整任务，按以下规则恢复：
  - `Executing` → 重置为 `Queued` 并重新入队。
  - `Queued` → 保持 `Queued` 并重新入队。
- 数据文件路径：`{app_data_dir}/task-manager/tasks.db`。

### 6. 任务仪表盘（Task Dashboard）

- 每个用户可查看**自己的**任务列表，支持筛选（状态、时间范围）与排序。
- **Owner**（系统管理员/应用所有者）可查看**所有用户的**任务列表。
- 列表字段：task_id、状态、进度、创建时间、预估时长、异常级别。
- 支持操作：查看详情、取消（仅 `Queued` 状态）、重试（仅 `Failed` 状态）。
- 仪表盘可通过命令行或 Web 界面展示（取决于宿主环境）。

### 7. 完成通知（Completion Notification）

任务进入 `Completed` 或 `Failed` 终态时，触发通知：

1. **Windows Toast 通知**：使用 Windows 原生 Toast 弹窗，内容包含任务摘要与结果状态。
2. **聊天消息追加**：在用户当前对话（chat channel）中追加一条系统消息，内容为任务完成状态与结果摘要。
- 通知在状态变更瞬间触发，不延迟。
- 用户可配置是否接收 Toast 通知（通过设置开关）。

---

## 设计原则

- **最小依赖**：仅依赖 SQLite，不引入 Redis / MQ 等外部中间件。
- **可观测性**：每个任务均记录完整时间线，便于排障。
- **安全隔离**：用户只能查看自己的任务；Owner 可全局查看。
- **优雅恢复**：应用重启不丢任务，不完整任务自动接续。
