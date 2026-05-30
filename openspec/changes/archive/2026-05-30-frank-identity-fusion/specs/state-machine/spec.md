# 状态机能力规范 - Phase 2 增量变更

## 概述

本文件是状态机能力规范的 Phase 2 增量变更。变更围绕身份融合引擎的引入，对认证逻辑、身份上下文传递、身份变更检测及角色感知状态转换进行修订和扩展。未在本文件中提及的规范内容以 Phase 1 基线为准。

---

## MODIFIED Requirements

### Requirement: 状态定义

系统必须定义四个离散状态，各自具有独立的行为特征和资源消耗策略。Auth 状态现承载身份上下文。

| 状态 | 名称 | 行为特征 |
|------|------|----------|
| Idle | 空闲 | 未检测到任何人，最小资源占用，摄像头以低频（1fps）运行，麦克风仅监听唤醒词 |
| Aware | 感知 | 检测到人（人脸或语音），摄像头提高频率至 5fps，活跃的 VAD + 唤醒词检测，身份融合引擎正在运行以确认身份 |
| Auth | 认证 | 身份已确认（身份融合引擎输出 confirmed identity），系统就绪等待指令，全量摄像头 + 麦克风管线激活。状态实例携带身份上下文：`{ person_id, display_name, role, confidence }` |
| Chat | 对话 | 活跃对话进行中，绕过唤醒词检测，持续监听，LLM 处理中。身份上下文继承自 Auth 的确认身份 |

#### Scenario: Idle 状态资源策略

- **WHEN** 系统启动且无人脸和语音活动
- **THEN** 系统处于 Idle 状态，摄像头以 1fps 运行，麦克风仅处理唤醒词检测，CPU/GPU 资源占用降至最低

#### Scenario: Aware 状态检测激活

- **WHEN** 人脸检测（MediaPipe 返回边界框）或语音活动（Silero VAD 触发）
- **THEN** 系统切换到 Aware 状态，摄像头频率升至 5fps，VAD 和唤醒词检测同时激活，身份融合引擎开始收集人脸/语音嵌入进行身份确认

#### Scenario: Auth 状态就绪（Phase 2）

- **WHEN** 身份融合引擎输出 confirmed identity，各模态置信度达到融合阈值（默认 0.85）
- **THEN** 系统进入 Auth 状态，携带身份上下文 `{ person_id, display_name, role, confidence }`，全量摄像头和麦克风管线开启，准备接收用户指令

#### Scenario: Chat 状态对话进行

- **WHEN** 唤醒词 "Hey Frank" 被检测到且系统处于 Auth 状态
- **THEN** 系统进入 Chat 状态，唤醒词被绕过，持续监听用户输入，LLM 处理模块启动，身份上下文继承自 Auth 状态

---

### Requirement: 状态转换

系统必须按照定义的转换规则在四个状态之间流转，每种转换由特定触发条件驱动。Aware 到 Auth 的转换现由身份融合引擎驱动，不再依赖固定 2s 人脸持续检测。

#### 转换规则表

| 源状态 | 目标状态 | 触发条件 | 说明 |
|--------|----------|----------|------|
| Idle | Aware | 人脸检测到（MediaPipe 返回边界框）OR 语音活动检测到（Silero VAD 触发） | 任一条件满足即转换 |
| Aware | Idle | 无人脸 AND 无语音持续 timeout_aware 秒 | 默认 30s 超时 |
| Aware | Auth | 身份融合引擎输出 confirmed identity，融合置信度 >= 阈值（默认 0.85） | 替代 Phase 1 的 2s 连续人脸检测。身份上下文包含 { person_id, display_name, role, confidence } |
| Auth | Chat | 唤醒词 "Hey Frank" 被检测到 | 需精确匹配唤醒词 |
| Chat | Auth | 最后一次响应后沉默 timeout_chat 秒 | 默认 5min |
| Chat | Auth（身份变更新流程） | 身份融合引擎在 Chat 状态下检测到 face/voice embedding 切换，emit "identity_changing" 事件，暂停对话，重新执行融合。新身份确认后，先转入 Auth(new_identity)，再由用户唤醒进入 Chat | 参见"身份变更检测"需求 |
| Auth | Idle | 无人脸持续 timeout_auth_to_idle 秒 | 默认 60s |

#### Scenario: Idle 到 Aware 人脸触发

- **WHEN** MediaPipe 模块在 Idle 状态下检测到人脸边界框
- **THEN** 系统从 Idle 转换为 Aware，触发 "state.changed" 事件，时间戳记录转换时刻

#### Scenario: Idle 到 Aware 语音触发

- **WHEN** Silero VAD 在 Idle 状态下检测到语音活动（无同时人脸检测）
- **THEN** 系统从 Idle 转换为 Aware，触发 "state.changed" 事件，trigger 字段标记为 "voice_activity"

#### Scenario: Aware 到 Idle 超时回归

- **WHEN** 系统在 Aware 状态下，连续 timeout_aware 秒（默认 30s）内无人脸检测且无语音活动
- **THEN** 系统从 Aware 回归 Idle，摄像头降回 1fps，麦克风仅监听唤醒词

#### Scenario: Aware 到 Auth 融合身份确认（Phase 2）

- **WHEN** 身份融合引擎在 Aware 状态下完成多模态融合，输出 confirmed identity，融合置信度 >= 阈值（默认 0.85）
- **THEN** 系统从 Aware 转换为 Auth，携带身份上下文 `{ person_id, display_name, role, confidence }`，触发 "state.changed" 事件，event 负载包含 identity 字段
- **NOTE** 2s 连续人脸检测逻辑已移除，替代为身份融合引擎的置信度阈值判断

#### Scenario: Auth 到 Chat 唤醒词触发

- **WHEN** 唤醒词检测模块在 Auth 状态下检测到 "Hey Frank"
- **THEN** 系统从 Auth 转换为 Chat，唤醒词检测临时绕过，进入持续监听模式，聊天身份上下文继承自 Auth

#### Scenario: Chat 到 Auth 沉默超时

- **WHEN** 系统在 Chat 状态下，最后一次 LLM 响应后沉默 timeout_chat 秒（默认 5min）
- **THEN** 系统从 Chat 降级为 Auth，重新激活唤醒词检测，等待下一次唤醒，Auth 保持原身份上下文

#### Scenario: Auth 到 Idle 超时降级

- **WHEN** 系统在 Auth 状态下，无人脸持续 timeout_auth_to_idle 秒（默认 60s）
- **THEN** 系统从 Auth 降级回 Idle，所有高频感知管线关闭，身份上下文清空

---

### Requirement: 状态变更事件通知

每次状态转换时，系统必须发出状态变更事件，并通过 WebSocket 推送到 Electron 前端。当转换为 Auth 状态时，事件负载包含身份上下文。

- 事件负载包含以下字段：
  - `from`: 源状态名称（字符串）
  - `to`: 目标状态名称（字符串）
  - `timestamp`: ISO 8601 格式时间戳（字符串）
  - `trigger`: 触发转换的具体原因（字符串）
  - `identity`: 身份上下文对象，当 to 为 Auth 时必填，其余状态为 null
    - `person_id`: 人员唯一标识（字符串）
    - `display_name`: 显示名称（字符串）
    - `role`: 角色标识（字符串）
    - 结构：`{ person_id, display_name, role } | null`

- Python 后端通过 WebSocket 推送消息类型 `"state.changed"`。

#### Scenario: 状态变更 WebSocket 推送（Auth 转换携带身份）

- **WHEN** 系统从 Aware 转换到 Auth，trigger 为 "identity_fusion_confirmed"，身份融合引擎确认用户 identity 为 `{ person_id: "usr_001", display_name: "Alice", role: "adult" }`
- **THEN** Python 后端构建事件对象：
  ```json
  {
    "from": "Aware",
    "to": "Auth",
    "timestamp": "2026-05-30T10:30:00.000Z",
    "trigger": "identity_fusion_confirmed",
    "identity": {
      "person_id": "usr_001",
      "display_name": "Alice",
      "role": "adult"
    }
  }
  ```
  通过 WebSocket 推送消息类型 `"state.changed"` 至 Electron 前端

#### Scenario: 状态变更 WebSocket 推送（非 Auth 转换 identity 为 null）

- **WHEN** 系统从 Chat 转换到 Auth（沉默超时），或从 Idle 转换到 Aware
- **THEN** Python 后端构建事件对象，identity 字段为 null：
  ```json
  {
    "from": "Idle",
    "to": "Aware",
    "timestamp": "2026-05-30T10:30:15.000Z",
    "trigger": "face_detected",
    "identity": null
  }
  ```

---

### Requirement: 状态查询接口

Electron 前端必须能够通过 WebSocket 主动查询当前状态，Python 后端需同步响应。

- 查询消息类型：`"state.get"`
- 响应消息类型：`"state.current"`
- 响应负载包含以下字段：
  - `state`: 当前状态名称（字符串）
  - `time_in_state`: 在当前状态的持续时长，单位为秒（数值）
  - `identity`: 当当前状态为 Auth 或 Chat 时包含身份上下文，否则为 null

#### Scenario: Electron 查询当前状态（Auth 带身份信息）

- **WHEN** Electron 前端发送消息类型 `"state.get"` 至 Python 后端，系统当前处于 Auth 状态
- **THEN** Python 后端响应消息类型 `"state.current"`，负载包含：
  ```json
  {
    "state": "Auth",
    "time_in_state": 12.5,
    "identity": {
      "person_id": "usr_001",
      "display_name": "Alice",
      "role": "adult"
    }
  }
  ```

---

### Requirement: 超时参数可配置

所有状态转换相关的超时参数必须可在配置文件 `config/frank.yaml` 的 `state_machine` 节中配置。Phase 2 移除 `timeout_auth` 参数（2s 连续人脸检测），新增身份融合相关参数。

#### 可配置参数清单

| 参数名 | 默认值 | 说明 |
|--------|--------|------|
| `timeout_aware` | 30 | Aware 状态下无人脸且无语音时回归 Idle 的超时秒数 |
| `timeout_chat` | 300 | Chat 状态下沉默后降级 Auth 的超时秒数（5分钟） |
| `timeout_auth_to_idle` | 60 | Auth 状态下无人脸时降级 Idle 的超时秒数 |
| `fusion_confidence_threshold` | 0.85 | 身份融合引擎输出 confirmed identity 所需的最小融合置信度 |

**注意**: Phase 1 的 `timeout_auth`（默认 2s）已移除。Aware 到 Auth 的转换不再依赖固定时长，由身份融合引擎根据实际融合置信度动态决定。

#### YAML 配置结构

```yaml
state_machine:
  timeout_aware: 30
  timeout_chat: 300
  timeout_auth_to_idle: 60
  fusion_confidence_threshold: 0.85
```

#### Scenario: 通过配置文件自定义融合置信度阈值

- **WHEN** 用户在 `config/frank.yaml` 中将 `state_machine.fusion_confidence_threshold` 修改为 `0.90`
- **THEN** 系统在下次启动（或配置热重载）后，身份融合引擎需要达到 0.90 的融合置信度方可确认身份并进入 Auth 状态

---

### Requirement: 状态转换日志记录

每次状态转换必须在 Python 日志中以 INFO 级别记录，包含触发原因和身份上下文（如适用）。

- 日志格式建议：`State transition: {from} -> {to} | trigger: {trigger} | identity: {identity} | timestamp: {timestamp}`

#### Scenario: 状态转换日志输出（Auth 带身份）

- **WHEN** 系统从 Aware 转换到 Auth，trigger 为 "identity_fusion_confirmed"，identity 为 `{ person_id: "usr_001", display_name: "Alice", role: "adult" }`
- **THEN** Python 日志输出：
  ```
  INFO  [state_machine] State transition: Aware -> Auth | trigger: identity_fusion_confirmed | identity: {"person_id":"usr_001","display_name":"Alice","role":"adult"} | timestamp: 2026-05-30T10:30:00.000Z
  ```

---

## ADDED Requirements

### Requirement: 身份变更检测

系统必须在 Chat 状态下持续监控身份一致性。当身份融合引擎检测到人脸或语音的 embedding 切换时，系统应当暂停对话、重新运行融合确认，并在确认新身份后流转至重新认证流程。

#### 身份变更事件流

| 步骤 | 说明 | 状态变化 |
|------|------|----------|
| 1 | 身份融合引擎在 Chat 状态下检测到 face/voice embedding 显著切换（与当前 Auth 身份不匹配） | 仍处于 Chat 状态 |
| 2 | 系统 emit "identity_changing" 事件，暂停当前 LLM 对话 | 仍处于 Chat 状态 |
| 3 | 系统向用户发出提示（例如 "身份确认中..."），同时身份融合引擎开始重新采集多模态数据进行融合 | 仍处于 Chat 状态 |
| 4 | 融合完成：若新身份确认且与当前身份不同，系统自动由 Chat 转换至 Auth(new_identity)，携带新身份上下文 | Chat -> Auth(new_identity) |
| 5 | Auth(new_identity) 状态等待用户通过唤醒词 "Hey Frank" 重新进入 Chat | Auth(new_identity) -> Chat |
| 6 | 若融合未达到置信度阈值，系统保持 Auth(原身份) 并通知用户身份确认失败，结束会话 | Chat -> Auth(原身份) |

#### Scenario: Chat 状态下身份变更检测与切换

- **WHEN** 系统处于 Chat 状态且身份为 `Alice`，身份融合引擎检测到当前 face 和 voice embedding 与 Alice 的注册嵌入不匹配，切换得分超过阈值（默认 0.7）
- **THEN** 系统按以下顺序执行：
  1. 触发内部事件 `"identity_changing"`，暂停 LLM 对话响应
  2. 身份融合引擎进入重新确认模式，在新的 face/voice 流上执行多模态融合
  3. 融合完成后：
     - 若新身份 `Bob` 被确认且融合置信度 >= 阈值（0.85），系统从 Chat 自动降级为 Auth，携带新身份上下文 `{ person_id: "usr_002", display_name: "Bob", role: "adult" }`，触发 "state.changed" 事件
     - 若融合未达到置信度阈值，系统降级为 Auth 保持原身份 `Alice`，触发 "state.changed" 事件并附带身份确认失败提示
  4. Auth 状态等待用户重新说出唤醒词以进入 Chat

#### Scenario: 身份变更 WebSocket 通知

- **WHEN** 系统 emit "identity_changing" 事件
- **THEN** Python 后端通过 WebSocket 推送消息类型 `"state.identity_changing"` 至 Electron 前端，负载包含：
  ```json
  {
    "previous_identity": {
      "person_id": "usr_001",
      "display_name": "Alice",
      "role": "adult"
    },
    "timestamp": "2026-05-30T10:35:00.000Z"
  }
  ```

---

### Requirement: 角色感知状态转换

当系统进入 Auth 状态时，状态机必须根据身份上下文中的 `role` 字段附加角色限定规则。角色决定 Chat 状态下可用的状态转换和行为约束。

#### 角色定义

| 角色标识 | 名称 | 说明 |
|----------|------|------|
| `adult` | 成人 | 全量功能可用，可触发所有状态转换 |
| `child` | 儿童 | 受限模式，无法触发某些状态转换 |
| `guest` | 访客 | 临时身份，有限交互权限 |

#### 角色感知转换规则

| 角色 | 允许的转换 | 限制说明 |
|------|-----------|----------|
| `adult` | 所有标准转换 | 无限制 |
| `child` | Idle ↔ Aware ↔ Auth ↔ Chat（标准流转），不可从 Chat 切换到涉及敏感权限的扩展状态 | 当未来引入涉及系统设置、隐私数据或付费功能的扩展状态时，child 角色不允许从 Chat 切换到该类状态。当前 Phase 2 仅需在状态上下文中记录 role 字段，限制逻辑预留扩展点 |
| `guest` | Idle ↔ Aware ↔ Auth ↔ Chat（标准流转），超时时长减半 | Chat 沉默超时降级为默认 150s（标准 5min 的一半），Auth 无人脸超时降级为默认 30s（标准 60s 的一半） |

#### Scenario: child 角色状态转换限制

- **WHEN** 系统处于 Auth 状态，身份上下文 role 为 `child`，用户说出唤醒词进入 Chat
- **THEN** Chat 状态继承 `role: "child"`，所有涉及系统设置修改、隐私数据访问或付费功能的未来转换在 child 角色下被阻止，系统角色继承标记记录在状态变更事件日志中

#### Scenario: guest 角色超时行为

- **WHEN** 系统处于 Auth 状态，身份上下文 role 为 `guest`
- **THEN** 在 Chat 状态下，沉默超时默认为 150s（timeout_chat 标准值 300s 的一半）；在 Auth 状态下，无人脸超时默认为 30s（timeout_auth_to_idle 标准值 60s 的一半）

#### Scenario: 角色上下文在状态变更事件中传递

- **WHEN** 状态由 Auth 转换为 Chat，身份上下文 role 为 `child`
- **THEN** "state.changed" 事件负载的 identity 字段包含 `{ person_id: "usr_003", display_name: "Charlie", role: "child" }`，Electron 前端可根据 role 字段调整 UI 展示和行为限制
