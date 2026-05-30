# 状态机能力规范（Phase 4 增量变更）

> **变更类型**: MODIFIED  
> **影响范围**: 新增多人状态分支，现有单用户线性流程（Idle / Aware / Auth / Chat）保持不变。  
> **实现阶段**: Phase 4 — Multi-Person State Branch

## 概述

Phase 4 在现有单用户状态机基础上，新增**多人状态分支**，使系统能够同时感知、识别并服务于多个人员。当环境中有两人及以上时，状态从单用户线性路径切换到多人分支，包含三个专属状态：Multi-Auth（多人认证）、Multi-Wait（静默命令等待）、Multi-Chat（并行对话会话）。当人数降回单人时，系统经过超时确认后回退到标准单用户 Chat 状态。

---

## ADDED Requirements

### Requirement: 多人状态定义

系统必须定义三个新的状态，构成多人分支路径。这些状态仅在检测到两人及以上人员时激活。

| 状态 | 名称 | 行为特征 |
|------|------|----------|
| Multi-Auth | 多人认证 | 识别环境中所有人员身份。摄像头全量运行，身份融合引擎对每个人独立执行融合确认。每个人员生成独立身份上下文 `{ person_id, display_name, role, confidence }`。Multi-Auth 持续到所有检测到的人员身份均被确认 |
| Multi-Wait | 静默命令等待 | 所有人员身份已确认，系统就绪等待指令。全量摄像头 + 麦克风管线激活。系统静默监听唤醒词或自然语言命令，不主动发言。维护全量身份列表 `[ { person_id, display_name, role }, ... ]` |
| Multi-Chat | 并行对话会话 | 活跃对话进行中。支持与**主要发言者（primary）** 和**次要发言者（secondary）** 的并行交互。每个会话继承各自的身份上下文。次要发言者在 Multi-Wait 中仍可静默等待 |

#### 事务条件对比

| 条件 | 单用户路径 | 多人路径 |
|------|-----------|----------|
| 检测到 0 人 | Idle | Idle（不变） |
| 检测到 1 人 | Aware → Auth → Chat | Aware → Auth → Chat（走现有路径） |
| 检测到 ≥2 人持续 ≥3s | — | Aware → Multi-Auth（切入多人分支） |
| Multi-Auth 全员身份确认 | — | Multi-Auth → Multi-Wait |
| 人数从 ≥2 降回 1 持续 ≥10s | — | 多人路径退出 → Chat（单用户） |

#### Scenario: Multi-Auth 多人认证流程

- **WHEN** 系统处于 Aware 状态，人脸检测（MediaPipe）同时返回 ≥2 个边界框且持续 ≥3 秒
- **THEN** 系统不进入标准 Auth 状态，而是切入 Multi-Auth 状态。身份融合引擎为每个检测到的人脸独立执行多模态身份确认（融合人脸 + 语音嵌入），每个人各自生成身份上下文 `{ person_id, display_name, role, confidence }`
- **AND** 当所有已检测人员的融合置信度均达到阈值（默认 0.85）后，全员身份确认完成，系统由 Multi-Auth 转换至 Multi-Wait

#### Scenario: Multi-Wait 静默等待多用户指令

- **WHEN** 系统处于 Multi-Auth 状态且所有人员身份均被确认
- **THEN** 系统进入 Multi-Wait 状态。全量摄像头和麦克风管线激活。系统保持静默（不主动发起对话），持续监听环境中任何人员的语音输入。维护可用人员身份列表：`{ persons: [ { person_id, display_name, role }, ... ] }`

#### Scenario: Multi-Chat 并行对话会话

- **WHEN** 主要发言者（primary，即第一个发出语音命令的人员）在 Multi-Wait 中说出唤醒词或自然语言命令
- **THEN** 系统为 primary 建立 Chat 会话，进入活跃对话；此时状态变为 **Chat + Multi-Wait** 混合态——primary 处于活跃对话中，secondary（其他已识别但未发言的人员）仍处于 Multi-Wait 静默等待状态
- **WHEN** 任意 secondary 在 Multi-Wait 中发出语音命令（无需唤醒词，因为环境内所有人员均已确认身份）
- **THEN** 系统为 secondary 也建立独立的 Chat 会话，进入 **Multi-Chat** 状态。每个发言者的对话会话彼此隔离，各自的 LLM 上下文独立维护

---

### Requirement: 多人状态转换规则

系统必须按照定义的转换规则在单用户路径和多人分支之间流转。新增转换以 **≥2 人持续 3 秒** 为切入条件，以 **人数降为 1 持续 10 秒** 为退出条件。

#### 转换规则表

| 源状态 | 目标状态 | 触发条件 | 说明 |
|--------|----------|----------|------|
| Aware | Multi-Auth（新增） | MediaPipe 检测到 ≥2 个人脸边界框且持续 ≥3 秒 | 从单用户路径切换到多人分支。标准 Aware→Auth 单用户转换被抢占 |
| Multi-Auth | Aware（回退） | 检测到的人脸数降为 1 且持续 ≥3 秒 | 若认证过程中人数降低，回退到 Aware 走单用户路径 |
| Multi-Auth | Multi-Wait | 所有已检测人员的身份融合置信度 ≥ 阈值（默认 0.85） | 全员确认完成，系统就绪 |
| Multi-Wait | Chat + Multi-Wait（混合态） | Primary（首个发言者）发出语音命令（含唤醒词或自然语言触发） | Primary 进入活跃对话，其余 Secondary 保持 Multi-Wait 静默等待 |
| Multi-Wait | Idle（回退） | 无人脸持续 timeout_multi_wait 秒 | 默认 30s，所有人员离开 |
| Chat + Multi-Wait | Multi-Chat | 任意 Secondary 发出语音命令 | Primary 继续对话，Secondary 加入并行会话 |
| Multi-Chat | Chat + Multi-Wait（降级） | 所有 Secondary 对话超时或结束，仅 Primary 继续 | Secondary 会话退出后回到混合态 |
| Chat + Multi-Wait | Multi-Wait（降级） | Primary 对话沉默超时（timeout_chat 默认 5min） | Primary 回到等待状态 |
| Multi-Chat | Multi-Wait（降级） | 所有对话超时或结束 | 全员回到等待状态 |
| Chat（单用户） | Multi-Auth（切入） | Chat 状态下检测到新人员加入，总人数 ≥2 持续 ≥3s | 从单用户对话切入多人认证。当前 Chat 会话暂停，身份融合引擎对新人员执行确认。确认完成后，原用户恢复 Chat + 新用户进入 Multi-Wait（Chat + Multi-Wait 混合态）。若新人员身份确认失败，仍保持单用户 Chat，记录日志 |
| 任意多人状态 | Chat（单用户退出，新增） | 检测到的人脸数降为 1 且持续 ≥10 秒 | 多人分支退出。当前所有会话结束，系统回退到单用户 Chat 状态，保留唯一剩余人员的身份上下文 |

#### Scenario: Aware 到 Multi-Auth 多人触发

- **WHEN** 系统处于 Aware 状态，人脸检测模块同时返回 ≥2 个边界框
- **THEN** 系统启动 3 秒连续检测计时器。若在这 3 秒内始终检测到 ≥2 人，计时到期后系统从 Aware 转换为 Multi-Auth，触发 "state.changed" 事件，`to` 字段为 "Multi-Auth"，`trigger` 字段为 "multi_person_detected_3s"，`identity` 字段为待确认人员空列表
- **AND** 若在计时期间人数降为 1，计时器取消，系统保持在 Aware，按现有单用户逻辑处理

#### Scenario: Multi-Auth 到 Multi-Wait 全员确认

- **WHEN** 系统处于 Multi-Auth 状态，身份融合引擎完成对所有已检测人员的身份确认，每个人的融合置信度均 ≥ 0.85
- **THEN** 系统从 Multi-Auth 转换为 Multi-Wait，触发 "state.changed" 事件，事件负载 `identity` 字段包含完整的人员列表：
  ```json
  {
    "from": "Multi-Auth",
    "to": "Multi-Wait",
    "timestamp": "2026-06-01T10:30:00.000Z",
    "trigger": "all_persons_identified",
    "identity": {
      "persons": [
        { "person_id": "usr_001", "display_name": "Alice", "role": "adult" },
        { "person_id": "usr_002", "display_name": "Bob", "role": "adult" }
      ]
    }
  }
  ```

#### Scenario: Multi-Wait 到 Chat + Multi-Wait 主发言者对话

- **WHEN** 系统处于 Multi-Wait 状态，Alice（person_id: usr_001）说出首次语音命令
- **THEN** 系统将 Alice 标记为 primary 发言者，为其建立 Chat 会话，进入 Chat + Multi-Wait 混合态。触发 "state.changed" 事件：
  ```json
  {
    "from": "Multi-Wait",
    "to": "Chat + Multi-Wait",
    "timestamp": "2026-06-01T10:30:10.000Z",
    "trigger": "primary_command",
    "identity": {
      "primary": { "person_id": "usr_001", "display_name": "Alice", "role": "adult" },
      "secondary": [
        { "person_id": "usr_002", "display_name": "Bob", "role": "adult" }
      ]
    }
  }
  ```
- **AND** Bob（secondary）继续处于 Multi-Wait 状态，系统静默等待其发出命令

#### Scenario: Multi-Wait 到 Multi-Chat 次要发言者加入

- **WHEN** 系统处于 Chat + Multi-Wait 混合态，secondary Bob 发出语音命令（无需唤醒词，因其身份已在 Multi-Auth 阶段确认）
- **THEN** 系统为 Bob 建立独立 Chat 会话，进入 Multi-Chat 状态。Alice 和 Bob 的对话会话彼此隔离，各自 LLM 上下文独立。触发 "state.changed" 事件，`to` 字段为 "Multi-Chat"

#### Scenario: 多人分支退出 — 人数降为 1 持续 10s

- **WHEN** 系统处于任意多人状态（Multi-Auth / Multi-Wait / Chat + Multi-Wait / Multi-Chat），人脸检测模块检测到人数降为 1
- **THEN** 系统启动 10 秒退出确认计时器。若 10 秒内人数始终为 1，计时到期后系统执行以下操作：
  1. 结束所有活跃的 Multi-Chat 会话，清理各自 LLM 上下文
  2. 推导唯一剩余人员的身份上下文
  3. 系统转换为单用户 Chat 状态，携带该人员的身份上下文
  4. 触发 "state.changed" 事件，`to` 字段为 "Chat"，`trigger` 字段为 "single_person_remained_10s"
- **AND** 若计时期间人数回升至 ≥2，计时器取消，系统维持当前多人状态

---

### Requirement: 多人状态变更事件通知

多人状态分支的所有状态转换必须通过 WebSocket 推送事件通知到 Electron 前端。事件负载在多人场景下须包含人员列表或多身份上下文。

#### 事件格式规范

| 事件类型 | 推送时机 | identity 字段格式 |
|----------|----------|-------------------|
| `state.changed` | 任何多人状态转换 | `from`/`to` 为多人状态名。`identity` 为对象：单人上下文 `{ person_id, display_name, role }`（回退到单用户时）或多人列表 `{ persons: [...] }`（多人状态间转换时） |
| `state.multi_person.joined` | 在多人状态中新人员身份确认完成 | `{ person_id, display_name, role }` |
| `state.multi_person.left` | 在多人状态中有人离开 | `{ person_id, display_name, role }`，附加 `persons_remaining: N` |
| `state.multi_person.session_started` | Multi-Chat 中新对话会话启动 | `{ person_id, display_name, role, session_id }` |
| `state.multi_person.session_ended` | Multi-Chat 中某对话会话结束 | `{ person_id, display_name, role, session_id, reason }` |

#### Scenario: 多人状态 WebSocket 推送（人员加入通知）

- **WHEN** 系统处于 Multi-Wait 或 Multi-Chat 状态，身份融合引擎确认新加入人员的身份（如新人员 Charlie 进入视野）
- **THEN** Python 后端通过 WebSocket 推送消息类型 `"state.multi_person.joined"`，负载：
  ```json
  {
    "person": { "person_id": "usr_003", "display_name": "Charlie", "role": "adult" },
    "total_persons": 3,
    "timestamp": "2026-06-01T10:31:00.000Z"
  }
  ```

#### Scenario: 多人状态 WebSocket 推送（人员离开通知）

- **WHEN** 系统处于多人状态，某人离开视野（人脸消失持续 timeout_person_left 秒，默认 5s）
- **THEN** Python 后端推送 `"state.multi_person.left"`，负载：
  ```json
  {
    "person": { "person_id": "usr_002", "display_name": "Bob", "role": "adult" },
    "persons_remaining": 1,
    "timestamp": "2026-06-01T10:32:00.000Z"
  }
  ```

#### Scenario: 多人状态 WebSocket 推送（并行会话启动/结束）

- **WHEN** Secondary 在 Multi-Wait 中发出语音命令，系统为其创建新的 Chat 会话
- **THEN** 后端推送 `"state.multi_person.session_started"`，负载：
  ```json
  {
    "session_id": "chat_sess_002",
    "person": { "person_id": "usr_002", "display_name": "Bob", "role": "adult" },
    "active_sessions": 2,
    "timestamp": "2026-06-01T10:33:00.000Z"
  }
  ```
- **WHEN** Bob 的会话因沉默超时或主动退出而结束
- **THEN** 后端推送 `"state.multi_person.session_ended"`，负载：
  ```json
  {
    "session_id": "chat_sess_002",
    "person": { "person_id": "usr_002", "display_name": "Bob", "role": "adult" },
    "active_sessions": 1,
    "reason": "timeout",
    "timestamp": "2026-06-01T10:38:00.000Z"
  }
  ```

---

### Requirement: 超时参数可配置 — 多人分支新增

在 `config/frank.yaml` 的 `state_machine` 节中新增以下可配置参数。

#### 新增可配置参数

| 参数名 | 默认值 | 说明 |
|--------|--------|------|
| `multi_person_detection_duration` | 3 | Aware 检测到 ≥2 人后切入 Multi-Auth 的持续确认秒数 |
| `multi_person_exit_duration` | 10 | 多人状态中人数降为 1 后回退单用户 Chat 的确认秒数 |
| `timeout_multi_wait` | 30 | Multi-Wait 状态下无人脸时退回到 Idle 的超时秒数 |
| `timeout_person_left` | 5 | 多人状态中某人离开视野到触发 `state.multi_person.left` 事件的超时秒数 |
| `timeout_multi_chat_session` | 600 | Multi-Chat 中单个会话最大持续时长（10分钟），超过后自动结束该会话 |

#### YAML 配置结构（增量）

```yaml
state_machine:
  # ... 现有参数保持不变 ...
  timeout_aware: 30
  timeout_chat: 300
  timeout_auth_to_idle: 60
  fusion_confidence_threshold: 0.85

  # Phase 4 新增参数
  multi_person_detection_duration: 3
  multi_person_exit_duration: 10
  timeout_multi_wait: 30
  timeout_person_left: 5
  timeout_multi_chat_session: 600
```

---

### Requirement: Chat 子状态兼容多人会话

Chat 状态的子状态链（Listening → Transcribing → Thinking → Speaking）在 Phase 4 Multi-Chat 中保持不变。每个并行会话各自拥有一套独立的子状态实例。

#### Multi-Chat 会话隔离规则

| 资源 | 隔离策略 | 说明 |
|------|----------|------|
| 音频流 | 独立 VAD 实例 | 每个会话的 VAD 基于声源分离（Speaker Diarization）绑定到特定人员 |
| STT 引擎 | 共享引擎，按会话队列 | 引擎实例共享，转录结果按 session_id 路由 |
| LLM 上下文 | 完全隔离 | 每个会话持有独立的对话历史和身份上下文 |
| TTS 输出 | 按人员路由 | 音频输出通过不同声道或语音标识区分不同发言者的响应 |
| 身份上下文 | 各自持有 | 每个会话绑定的身份上下文在该会话生命周期内不变 |

#### Scenario: Multi-Chat 下 Alice 和 Bob 并行交互

- **WHEN** 系统处于 Multi-Chat 状态，Alice 和 Bob 各自在独立会话中与系统对话
- **THEN** 系统维护两套独立的子状态实例：
  1. Alice 的会话可能处于 Speaking（系统正在回答 Alice），TTS 播放 Alice 语言的响应
  2. Bob 的会话可能处于 Transcribing（系统正在处理 Bob 的语音输入）
- **AND** 两套管线的音频输入通过声源分离绑定到各自的 speaker，互不干扰。TTS 输出的音频可通过定向扬声器或语音标记（如"Alice，你的答案是..."）区分

---

### Requirement: 多人状态退出后的身份恢复

当多人分支退出回退到单用户 Chat 时，系统必须正确推导并保持唯一剩余人员的身份上下文。若有多人同时在场但系统判定人数降为 1，仅保留最后离开视野的人员身份。

#### Scenario: 多人退出身份推导

- **WHEN** 系统处于 Multi-Chat，Alice 和 Bob 两人在场。Bob 离开视野，Alice 仍在
- **THEN** 以下序列执行：
  1. Bob 人脸消失持续 timeout_person_left（5s），触发 `state.multi_person.left` 事件（Bob 离开）
  2. 此时剩余 1 人（Alice），启动 10s 退出确认计时器
  3. 10 秒内 Alice 始终在场，计时到期
  4. 系统结束 Bob 的活跃会话，清理其 LLM 上下文
  5. 系统从 Multi-Chat 转换为 Chat，身份上下文设置为 Alice 的 `{ person_id: "usr_001", display_name: "Alice", role: "adult" }`
  6. 触发 `state.changed` 事件，`to` 为 "Chat"，`identity` 为 Alice 的单人上下文

---

### Requirement: 多人状态日志记录

所有多人状态转换必须记录详细日志，包含触发原因、涉及人员列表及数量。

- 日志格式建议：`State transition (multi): {from} -> {to} | trigger: {trigger} | persons: [{person_id}, ...] | count: {N} | timestamp: {timestamp}`

#### Scenario: 多人状态转换日志

- **WHEN** 系统从 Multi-Auth 转换到 Multi-Wait，trigger 为 "all_persons_identified"，涉及 Alice 和 Bob
- **THEN** Python 日志输出：
  ```
  INFO  [state_machine] State transition (multi): Multi-Auth -> Multi-Wait | trigger: all_persons_identified | persons: [usr_001, usr_002] | count: 2 | timestamp: 2026-06-01T10:30:00.000Z
  ```

---

### Requirement: 多人状态查询接口增强

Electron 前端通过 WebSocket 查询当前状态时（`state.get`），多人状态下的响应负载必须扩展。

#### 响应负载增强

| 字段 | 类型 | 多人状态下取值 |
|------|------|--------------|
| `state` | 字符串 | Multi-Auth / Multi-Wait / Chat + Multi-Wait / Multi-Chat |
| `time_in_state` | 数值 | 在当前状态的持续秒数 |
| `persons` | 对象数组 | 当前所有已识别的人员列表 `[{ person_id, display_name, role, status }]` |
| `active_sessions` | 数值 | 当前活跃的 Chat 会话数量（仅 Multi-Chat 和混合态时 >0） |
| `identity` | 对象/null | 仅在回退到单用户 Chat 或 Auth 时设置，多人状态下为 null |

#### Scenario: Electron 查询 Multi-Chat 状态

- **WHEN** Electron 前端发送 `state.get`，系统当前处于 Multi-Chat，Alice 和 Bob 均有活跃会话
- **THEN** Python 后端响应：
  ```json
  {
    "state": "Multi-Chat",
    "time_in_state": 45.2,
    "persons": [
      { "person_id": "usr_001", "display_name": "Alice", "role": "adult", "status": "chatting" },
      { "person_id": "usr_002", "display_name": "Bob", "role": "adult", "status": "chatting" }
    ],
    "active_sessions": 2,
    "identity": null
  }
  ```

#### Scenario: Electron 查询 Chat + Multi-Wait 混合态

- **WHEN** Electron 前端发送 `state.get`，系统当前处于 Chat + Multi-Wait，Alice 在对话中，Bob 在等待
- **THEN** Python 后端响应：
  ```json
  {
    "state": "Chat + Multi-Wait",
    "time_in_state": 12.0,
    "persons": [
      { "person_id": "usr_001", "display_name": "Alice", "role": "adult", "status": "chatting" },
      { "person_id": "usr_002", "display_name": "Bob", "role": "adult", "status": "waiting" }
    ],
    "active_sessions": 1,
    "identity": null
  }
  ```
