# 状态机能力规范

## 概述

Phase 4 在现有单用户状态机基础上，新增**多人状态分支**，使系统能够同时感知、识别并服务于多个人员。当环境中有两人及以上时，状态从单用户线性路径切换到多人分支，包含三个专属状态：Multi-Auth（多人认证）、Multi-Wait（静默命令等待）、Multi-Chat（并行对话会话）。当人数降回单人时，系统经过超时确认后回退到标准单用户 Chat 状态。

## 架构位置

状态机运行于 Python 后端进程，通过 WebSocket 与 Electron 前端通信。

---

## ADDED Requirements

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

- **WHEN** 唤醒词 "Hey Frank" 被检测到（可从任意状态触发）
- **THEN** 系统进入 Chat 状态，唤醒词被绕过，持续监听用户输入，LLM 处理模块启动。如在 Auth 状态则继承已确认的身份上下文，否则以 guest 身份运行

---

### Requirement: 状态转换

系统必须按照定义的转换规则在四个状态之间流转，每种转换由特定触发条件驱动。Aware 到 Auth 的转换现由身份融合引擎驱动，不再依赖固定 2s 人脸持续检测。**唤醒词 "Hey Frank" 被检测到时，系统 MUST 从任意状态（Idle、Aware、Auth、Chat）转入 Chat 状态**，而非仅从 Auth/Chat 状态。

#### 转换规则表

| 源状态 | 目标状态 | 触发条件 | 说明 |
|--------|----------|----------|------|
| Idle | Aware | 人脸检测到（MediaPipe 返回边界框）OR 语音活动检测到（Silero VAD 触发） | 任一条件满足即转换 |
| Idle | Chat | 唤醒词 "Hey Frank" 被检测到 | 新增: 免人脸直接通过语音唤醒进入对话 |
| Aware | Idle | 无人脸 AND 无语音持续 timeout_aware 秒 | 默认 30s 超时 |
| Aware | Auth | 身份融合引擎输出 confirmed identity，融合置信度 >= 阈值（默认 0.85） | 替代 Phase 1 的 2s 连续人脸检测。身份上下文包含 { person_id, display_name, role, confidence } |
| Aware | Chat | 唤醒词 "Hey Frank" 被检测到 | 新增: 无需等待身份确认即可唤醒 |
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

#### Scenario: Idle 状态下唤醒词直接进入 Chat

- **WHEN** 系统处于 Idle 状态（无人脸检测），用户说出 "Hey Frank"
- **THEN** 系统从 Idle 转入 Chat 状态，唤醒词检测器触发，对话编排器启动，身份暂为 guest

#### Scenario: Aware 状态下唤醒词进入 Chat

- **WHEN** 系统处于 Aware 状态（人脸已检测但身份尚未确认），用户说出 "Hey Frank"
- **THEN** 系统从 Aware 转入 Chat 状态，对话以当前检测到的身份上下文（如有）或 guest 身份运行

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

---

### Requirement: Chat 子状态定义

Chat 状态必须分解为四个顺序流转的子状态，分别对应对话管道中的不同处理阶段。每个子状态具有独立的语义和行为特征。

| 子状态 | 名称 | 行为特征 |
|--------|------|----------|
| Listening | 等待语音输入 | 麦克风持续监听，VAD 激活，检测用户语音端点。身份上下文（来自 Auth）保持有效 |
| Transcribing | 语音识别中 | STT（语音转文字）引擎处理音频缓冲区，输出文本转录。用户语音结束（voice_end）触发进入此状态 |
| Thinking | LLM 推理中 | LLM 处理转录文本，生成响应。转录完成（transcription_done）触发进入此状态 |
| Speaking | TTS 播放中 | TTS（文字转语音）引擎播放 LLM 响应音频。响应就绪（response_ready）触发进入此状态。播放完成后（tts_done）回到 Listening |

#### Scenario: Listening 状态语音检测

- **WHEN** 系统处于 Chat 状态中的 Listening 子状态，Silero VAD 检测到用户开始说话
- **THEN** 系统开始录音缓冲，等待语音结束端点（voice_end），在此期间身份上下文保持为继承自 Auth 的值

#### Scenario: Transcribing 状态 STT 处理

- **WHEN** 系统检测到语音结束（voice_end 事件），从 Listening 进入 Transcribing 子状态
- **THEN** STT 引擎处理累积的音频缓冲区，输出文本转录。处理期间音频输入暂停，直至完成

#### Scenario: Thinking 状态 LLM 推理

- **WHEN** STT 引擎完成转录（transcription_done 事件），从 Transcribing 进入 Thinking 子状态
- **THEN** LLM 接收转录文本和身份上下文，开始生成响应。此阶段前端可展示"思考中"或"输入中"指示器

#### Scenario: Speaking 状态 TTS 播放

- **WHEN** LLM 生成完整响应（response_ready 事件），从 Thinking 进入 Speaking 子状态
- **THEN** TTS 引擎将响应文本合成为音频并播放。播放期间，麦克风暂时静音以避免回声。播放完成后（tts_done 事件），系统回到 Listening 子状态，等待下一轮用户输入

---

### Requirement: 对话循环

Chat 状态必须实现完整的对话循环管道，由连续的事件驱动流转。每个完整的对话轮次包含一次 Listening → Transcribing → Thinking → Speaking → Listening 循环。

#### 对话循环事件流

```
Listening ──(voice_end)──→ Transcribing ──(transcription_done)──→ Thinking ──(response_ready)──→ Speaking ──(tts_done)──→ Listening（循环）
```

| 步骤 | 事件 | 源子状态 | 目标子状态 | 说明 |
|------|------|----------|------------|------|
| 1 | wake_word 检测到 | （进入 Chat） | Listening | 唤醒词触发进入 Chat 状态，初始化为 Listening 子状态 |
| 2 | voice_end | Listening | Transcribing | 用户停止说话，语音端点检测触发 |
| 3 | transcription_done | Transcribing | Thinking | STT 完成文本输出 |
| 4 | response_ready | Thinking | Speaking | LLM 生成完整响应 |
| 5 | tts_done | Speaking | Listening | TTS 播放完成，新一轮循环开始 |

#### Scenario: 单轮对话循环

- **WHEN** 系统进入 Chat 状态（Listening），用户说出"今天天气如何"并沉默
- **THEN** 以下事件序列依次发生：
  1. VAD 检测语音结束 → `voice_end` 事件 → 进入 Transcribing
  2. STT 引擎输出文本 `"今天天气如何"` → `transcription_done` 事件 → 进入 Thinking
  3. LLM 生成响应 `"今天晴，25°C"` → `response_ready` 事件 → 进入 Speaking
  4. TTS 引擎播放语音响应完成 → `tts_done` 事件 → 回到 Listening，等待下一轮用户输入

#### Scenario: 多轮连续对话

- **WHEN** 系统在 Chat 状态下完成一轮对话并回到 Listening，用户立即继续说话
- **THEN** 循环自动重复步骤 2—5，身份上下文在整段对话期间保持不变，无需重新唤醒

#### Scenario: 对话循环异常处理 — 转录失败

- **WHEN** 系统在 Transcribing 子状态时 STT 引擎返回错误或空转录（transcription_failed 事件）
- **THEN** 系统 emit "state.chat.transcription_failed" 事件，回退到 Listening 子状态，等待用户重新输入，同时可向用户发出提示"未听清，请再说一遍"

#### Scenario: 对话循环异常处理 — LLM 超时

- **WHEN** 系统在 Thinking 子状态时 LLM 响应超过 timeout_llm 秒（默认 10s），触发 llm_timeout 事件
- **THEN** 系统 emit "state.chat.llm_timeout" 事件，回退到 Listening 子状态，并可向用户发出提示"处理超时，请重试"

---

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

---

## ADDED Requirements (Phase 5)

### Requirement: 手势驱动的状态转换
状态机 SHALL 新增 `gesture_detected` 事件，支持手势驱动的状态转换。预定义手势 `come_closer` SHALL 可触发 Idle → Aware 转换。

#### Scenario: 走近手势激活系统
- **WHEN** 系统处于 Idle 状态
- **AND** 摄像头检测到 `come_closer` 手势（人脸 bbox 持续增大 + Z 深度减小）
- **THEN** 系统从 Idle 转换到 Aware，trigger 标记为 `"gesture_come_closer"`

#### Scenario: 举手手势暂停对话
- **WHEN** 系统处于 Chat 状态
- **AND** 检测到 `raise_hand` 手势
- **THEN** 系统暂停当前对话循环（LLM 和 TTS 停止），进入 Chat 暂停子状态

#### Scenario: 非激活状态忽略其他手势
- **WHEN** 系统处于 Idle 状态
- **AND** 检测到 `wave` 或 `point` 手势（非 `come_closer`）
- **THEN** 手势被忽略，不触发状态转换

### Requirement: 手势事件传播
状态机 SHALL 在接收到 `gesture_detected` 事件时，校验手势类型与当前状态是否匹配，匹配时执行对应转换并广播 `state.changed` 事件，trigger 字段标记为 `"gesture_{type}"`。

#### Scenario: 手势状态变更广播
- **WHEN** `come_closer` 手势触发 Idle → Aware 转换
- **THEN** 状态机广播 `state.changed` 事件：
  ```json
  {
    "from": "Idle",
    "to": "Aware",
    "trigger": "gesture_come_closer",
    "identity": null
  }
  ```

#### Scenario: 手势日志记录
- **WHEN** 任何手势驱动的状态转换发生
- **THEN** Python 日志以 INFO 级别记录：`State transition: {from} -> {to} | trigger: gesture_{type} | timestamp: {iso_time}`
