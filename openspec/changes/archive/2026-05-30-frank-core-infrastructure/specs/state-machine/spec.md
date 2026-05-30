# 状态机能力规范

## 概述

Frank 核心状态机负责管理系统的感知和交互状态。状态机采用线性流转模型，包含四个状态：Idle（空闲）、Aware（感知）、Auth（认证）、Chat（对话）。Phase 1 暂不支持多人分支场景，仅实现单用户线性流程。

## 架构位置

状态机运行于 Python 后端进程，通过 WebSocket 与 Electron 前端通信。

---

## ADDED Requirements

### Requirement: 状态定义

系统必须定义四个离散状态，各自具有独立的行为特征和资源消耗策略。

| 状态 | 名称 | 行为特征 |
|------|------|----------|
| Idle | 空闲 | 未检测到任何人，最小资源占用，摄像头以低频（1fps）运行，麦克风仅监听唤醒词 |
| Aware | 感知 | 检测到人（人脸或语音），摄像头提高频率至 5fps，活跃的 VAD + 唤醒词检测，身份正在确定中 |
| Auth | 认证 | 身份已确认（Phase 1 简化为 face_detected=true 即进入 Auth），系统就绪等待指令，全量摄像头 + 麦克风管线激活 |
| Chat | 对话 | 活跃对话进行中，绕过唤醒词检测，持续监听，LLM 处理（Phase 1 为占位） |

#### Scenario: Idle 状态资源策略

- **WHEN** 系统启动且无人脸和语音活动
- **THEN** 系统处于 Idle 状态，摄像头以 1fps 运行，麦克风仅处理唤醒词检测，CPU/GPU 资源占用降至最低

#### Scenario: Aware 状态检测激活

- **WHEN** 人脸检测（MediaPipe 返回边界框）或语音活动（Silero VAD 触发）
- **THEN** 系统切换到 Aware 状态，摄像头频率升至 5fps，VAD 和唤醒词检测同时激活

#### Scenario: Auth 状态就绪

- **WHEN** 身份确认完成（Phase 1 简化为 face_detected=true 持续达到超时阈值）
- **THEN** 系统进入 Auth 状态，全量摄像头和麦克风管线开启，准备接收用户指令

#### Scenario: Chat 状态对话进行

- **WHEN** 唤醒词 "Hey Frank" 被检测到且系统处于 Auth 状态
- **THEN** 系统进入 Chat 状态，唤醒词被绕过，持续监听用户输入，LLM 处理模块启动（Phase 1 为占位实现）

---

### Requirement: 状态转换

系统必须按照定义的转换规则在四个状态之间流转，每种转换由特定触发条件驱动。

#### 转换规则表

| 源状态 | 目标状态 | 触发条件 | 说明 |
|--------|----------|----------|------|
| Idle | Aware | 人脸检测到（MediaPipe 返回边界框）OR 语音活动检测到（Silero VAD 触发） | 任一条件满足即转换 |
| Aware | Idle | 无人脸 AND 无语音持续 timeout_aware 秒 | 默认 30s 超时 |
| Aware | Auth | 人脸持续检测到 timeout_auth 秒 | 默认 2s 连续检测，Phase 1 简化方案 |
| Auth | Chat | 唤醒词 "Hey Frank" 被检测到 | 需精确匹配唤醒词 |
| Chat | Auth | 最后一次响应后沉默 timeout_chat 秒 | 默认 5min |
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

#### Scenario: Aware 到 Auth 持续人脸确认

- **WHEN** MediaPipe 在 Aware 状态下连续检测到人脸达到 timeout_auth 秒（默认 2s）
- **THEN** 系统从 Aware 转换为 Auth，触发 "state.changed" 事件

#### Scenario: Auth 到 Chat 唤醒词触发

- **WHEN** 唤醒词检测模块在 Auth 状态下检测到 "Hey Frank"
- **THEN** 系统从 Auth 转换为 Chat，唤醒词检测临时绕过，进入持续监听模式

#### Scenario: Chat 到 Auth 沉默超时

- **WHEN** 系统在 Chat 状态下，最后一次 LLM 响应后沉默 timeout_chat 秒（默认 5min）
- **THEN** 系统从 Chat 降级为 Auth，重新激活唤醒词检测，等待下一次唤醒

#### Scenario: Auth 到 Idle 超时降级

- **WHEN** 系统在 Auth 状态下，无人脸持续 timeout_auth_to_idle 秒（默认 60s）
- **THEN** 系统从 Auth 降级回 Idle，所有高频感知管线关闭

---

### Requirement: 状态变更事件通知

每次状态转换时，系统必须发出状态变更事件，并通过 WebSocket 推送到 Electron 前端。

- 事件负载包含以下字段：
  - `from`: 源状态名称（字符串）
  - `to`: 目标状态名称（字符串）
  - `timestamp`: ISO 8601 格式时间戳（字符串）
  - `trigger`: 触发转换的具体原因（字符串）

- Python 后端通过 WebSocket 推送消息类型 `"state.changed"`。

#### Scenario: 状态变更 WebSocket 推送

- **WHEN** 系统发生任意状态转换（例如从 Aware 转换到 Auth，trigger 为 "face_detected_continuous"）
- **THEN** Python 后端构建事件对象 `{"from": "Aware", "to": "Auth", "timestamp": "2026-05-30T10:30:00.000Z", "trigger": "face_detected_continuous"}`，通过 WebSocket 推送消息类型 `"state.changed"` 至 Electron 前端

---

### Requirement: 状态查询接口

Electron 前端必须能够通过 WebSocket 主动查询当前状态，Python 后端需同步响应。

- 查询消息类型：`"state.get"`
- 响应消息类型：`"state.current"`
- 响应负载包含以下字段：
  - `state`: 当前状态名称（字符串）
  - `time_in_state`: 在当前状态的持续时长，单位为秒（数值）

#### Scenario: Electron 查询当前状态

- **WHEN** Electron 前端发送消息类型 `"state.get"` 至 Python 后端
- **THEN** Python 后端响应消息类型 `"state.current"`，负载包含 `{"state": "Aware", "time_in_state": 12.5}`，表示当前处于 Aware 状态且已持续 12.5 秒

---

### Requirement: 超时参数可配置

所有状态转换相关的超时参数必须可在配置文件 `config/frank.yaml` 的 `state_machine` 节中配置。

#### 可配置参数清单

| 参数名 | 默认值 | 说明 |
|--------|--------|------|
| `timeout_aware` | 30 | Aware 状态下无人脸且无语音时回归 Idle 的超时秒数 |
| `timeout_auth` | 2 | Aware 状态下持续检测人脸进入 Auth 的确认秒数（Phase 1） |
| `timeout_chat` | 300 | Chat 状态下沉默后降级 Auth 的超时秒数（5分钟） |
| `timeout_auth_to_idle` | 60 | Auth 状态下无人脸时降级 Idle 的超时秒数 |

#### YAML 配置结构

```yaml
state_machine:
  timeout_aware: 30
  timeout_auth: 2
  timeout_chat: 300
  timeout_auth_to_idle: 60
```

#### Scenario: 通过配置文件自定义超时

- **WHEN** 用户在 `config/frank.yaml` 中将 `state_machine.timeout_aware` 修改为 `60`
- **THEN** 系统在下次启动（或配置热重载）后，Aware 到 Idle 的超时阈值变为 60 秒，替代默认的 30 秒

---

### Requirement: 状态转换日志记录

每次状态转换必须在 Python 日志中以 INFO 级别记录，包含触发原因。

- 日志格式建议：`State transition: {from} -> {to} | trigger: {trigger} | timestamp: {timestamp}`

#### Scenario: 状态转换日志输出

- **WHEN** 系统从 Auth 转换到 Chat，trigger 为 "wake_word_detected"
- **THEN** Python 日志输出 `INFO  [state_machine] State transition: Auth -> Chat | trigger: wake_word_detected | timestamp: 2026-05-30T10:30:00.000Z`
