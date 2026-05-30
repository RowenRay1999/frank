# 状态机能力规范 — Phase 3 Delta

## 概述

本文档为 Phase 3 状态机增量变更规范。基于 Phase 2 基础状态机（Idle / Aware / Auth / Chat），Phase 3 对 Chat 状态进行细化分解，引入对话子状态和完整的对话循环管道，并新增 Chat 内的会话超时触发 Chat→Auth 转换。

---

## ADDED Requirements

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

### Requirement: 对话事件通知

每次 Chat 子状态转换时，系统必须通过 WebSocket 发出子状态变更事件，允许 Electron 前端更新 UI 指示器（如麦克风图标、转写文本、思考动画、TTS 状态）。

- WebSocket 消息类型：`"state.chat.sub_state"`（Phase 3 新增）
- 消息负载：
  - `sub_state`：当前子状态名称（"listening"、"transcribing"、"thinking"、"speaking"）
  - `timestamp`：ISO 8601 格式时间戳（字符串）
  - `transcript`：Transcribing 子状态完成时的文本输出（可选，仅 transcription_done 时出现）
  - `session_id`：当前对话会话的唯一标识（字符串）

#### Scenario: 子状态变更推送至前端

- **WHEN** 系统从 Listening 转换到 Transcribing（voice_end 事件）
- **THEN** Python 后端通过 WebSocket 推送消息类型 `"state.chat.sub_state"`：
  ```json
  {
    "sub_state": "transcribing",
    "timestamp": "2026-05-30T10:30:05.000Z",
    "session_id": "sess_20260530_001"
  }
  ```

#### Scenario: Thinking 子状态附带转录文本

- **WHEN** 系统从 Transcribing 转换到 Thinking（transcription_done 事件），转录文本为 `"今天天气如何"`
- **THEN** 推送负载包含 transcript 字段：
  ```json
  {
    "sub_state": "thinking",
    "timestamp": "2026-05-30T10:30:06.000Z",
    "transcript": "今天天气如何",
    "session_id": "sess_20260530_001"
  }
  ```

---

## MODIFIED Requirements

### Requirement: 状态定义（Chat 状态更新）

Chat 状态的描述必须更新，以反映子状态分解和对话循环机制。

**变更前描述：**

| Chat | 对话 | 活跃对话进行中，绕过唤醒词检测，持续监听，LLM 处理中。身份上下文继承自 Auth 的确认身份 |

**变更后描述：**

| Chat | 对话 | 活跃对话进行中，绕过唤醒词检测。Chat 状态内部分解为 Listening → Transcribing → Thinking → Speaking 四个子状态，构成完整的对话循环管道。身份上下文继承自 Auth 的确认身份 |

#### Scenario: Chat 子状态整体描述

- **WHEN** 系统从 Auth 转换到 Chat（唤醒词触发）
- **THEN** Chat 状态初始化为 Listening 子状态，携带继承自 Auth 的身份上下文 `{ person_id, display_name, role, confidence }`，开始完整的对话循环生命周期

---

### Requirement: 状态转换（Chat→Auth 转换条件新增）

Chat→Auth 的转换规则必须新增一条触发条件：对话超时。

**原有转换规则（Phase 2）：**

| 源状态 | 目标状态 | 触发条件 | 说明 |
|--------|----------|----------|------|
| Chat | Auth | 最后一次响应后沉默 timeout_chat 秒 | 默认 5min |

**新增转换条件（Phase 3，补充到现有规则上方）：**

| 源状态 | 目标状态 | 触发条件 | 说明 |
|--------|----------|----------|------|
| Chat | Auth | 对话超时：Listening 子状态下连续无语音输入超过 timeout_conversation_silence 秒 | 默认 30s。用户在 Chat 状态下开始对话后，如果在 Listening 子状态连续 30 秒未检测到语音输入，则触发对话超时降级。此超时独立于现有的 timeout_chat（Chat 整体沉默超时） |

#### Scenario: Chat 对话超时降级

- **WHEN** 系统处于 Chat 状态下的 Listening 子状态，连续 timeout_conversation_silence 秒（默认 30s）未检测到用户语音输入（VAD 无反应用户语音起始）
- **THEN** 系统从 Chat 降级为 Auth，触发 "state.changed" 事件，trigger 字段标记为 "conversation_timeout"，身份上下文保持不变

#### Scenario: Chat 对话超时与 Chat 整体沉默超时的区别

- **WHEN** 系统在 Chat 状态 Listening 子状态连续 30s 无语音输入（timeout_conversation_silence 触发）
- **THEN** 系统降级到 Auth（对话超时），身份上下文保持，唤醒词检测重新激活，用户可通过唤醒词再次进入 Chat

- **WHEN** 系统最后一次 LLM 响应完成后，用户既未在 Listening 中输入语音也未明确离开，且总沉默时间达到 timeout_chat（默认 5min）
- **THEN** 系统降级到 Auth（整体沉默超时），与原 Phase 2 行为一致，身份上下文保持

---

### Requirement: 超时参数更新（Phase 3 新增参数）

`config/frank.yaml` 的 `state_machine` 节必须新增以下可配置参数：

| 参数名 | 默认值 | 说明 |
|--------|--------|------|
| `timeout_conversation_silence` | 30 | Chat 状态下 Listening 子状态连续无语音输入的对话超时秒数，触发 Chat→Auth 降级 |
| `timeout_llm` | 10 | Chat 状态下 Thinking 子状态等待 LLM 响应的超时秒数，超时则回退到 Listening |

#### YAML 配置结构（Phase 3 新增）

```yaml
state_machine:
  # ... Phase 2 参数保持不变 …
  timeout_conversation_silence: 30
  timeout_llm: 10
```

#### Scenario: 通过配置文件自定义对话超时

- **WHEN** 用户在 `config/frank.yaml` 中将 `state_machine.timeout_conversation_silence` 修改为 `20`
- **THEN** 系统在下次启动（或配置热重载）后，Chat 状态下 Listening 子状态连续 20 秒无语音输入即触发对话超时降级
