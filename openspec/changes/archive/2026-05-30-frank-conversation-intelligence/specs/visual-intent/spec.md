# 视觉意图感知 (Visual Intent) — Phase 3

## ADDED Requirements

### Requirement: 视线检测 (Gaze Detection)

系统 SHALL 使用 MediaPipe Face Mesh 的 468 个面部关键点，提取双眼中心位置及虹膜位置，计算视线方向向量（gaze vector）。当视线与摄像头法线夹角小于 10 度且持续时间超过 2 秒时，系统 SHALL 发射 `visual.gaze_detected` 事件。该事件用于辅助唤醒词触发逻辑：视线 + 语音联合触发时可绕过唤醒词要求。

#### Scenario: 用户注视摄像头超过 2 秒

- **WHEN** 用户面部正对摄像头，视线方向向量与摄像头法线夹角持续小于 10°
- **THEN** 系统在 2 秒条件满足后立即发射 `visual.gaze_detected` 事件，事件载荷包含 `{ angle: float, duration_ms: int, confidence: float }`

#### Scenario: 短暂注视后移开视线

- **WHEN** 用户注视摄像头 1.2 秒后移开视线，未达到 2 秒阈值
- **THEN** 系统不发射 `visual.gaze_detected` 事件，注视计时器重置

#### Scenario: 视线持续保持

- **WHEN** 用户持续注视摄像头超过 2 秒，且注视状态一直保持
- **THEN** 系统仅在首次达到阈值时发射一次 `visual.gaze_detected` 事件，不重复发射，直到注视丢失后重新累计

#### Scenario: 注视丢失

- **WHEN** 用户视线移开，角度大于 10° 持续超过 500ms
- **THEN** 系统发射 `visual.gaze_lost` 事件，注视计时器重置

### Requirement: 点头检测 (Nod Detection)

系统 SHALL 追踪鼻尖关键点（Landmark #1）在画面中的 Y 轴位置变化，跨帧计算运动轨迹。在 1 秒时间窗口内检测到先向上再向下的运动模式时，系统 SHALL 发射 `visual.nod` 事件，附带置信度分数。该事件用于确认/肯定意图，配合问答场景中的"是"确认。

#### Scenario: 检测到点头动作

- **WHEN** 用户在 1 秒窗口内完成鼻尖 Y 坐标先下降（抬头）再上升（低头），且 Y 轴位移幅度 > 阈值（默认 15 像素）
- **THEN** 系统发射 `visual.nod` 事件，载荷包含 `{ confidence: float }`，置信度基于位移幅度与运动速度计算

#### Scenario: 头部自然晃动不误判

- **WHEN** 用户头部有小幅度自然活动，Y 轴位移 < 15 像素阈值
- **THEN** 系统不发射 `visual.nod` 事件

#### Scenario: 连续点头

- **WHEN** 用户在 2 秒内完成 2 次点头动作
- **THEN** 系统为每次有效点头分别发射 `visual.nod` 事件，并在逻辑层允许将连续点头视为更高置信度的确认信号

### Requirement: 摇头检测 (Head Shake Detection)

系统 SHALL 追踪鼻尖关键点（Landmark #1）在画面中的 X 轴位置变化，跨帧计算运动轨迹。在 1 秒时间窗口内检测到先左再右再左（或反之）的往复运动模式时，系统 SHALL 发射 `visual.shake` 事件。该事件用于拒绝/取消意图，配合问答场景中的"否"确认。

#### Scenario: 检测到摇头动作

- **WHEN** 用户在 1 秒窗口内完成鼻尖 X 坐标的完整往复运动序列（左-右-左或右-左-右），且每次方向反转时的 X 轴累积位移幅度 > 阈值（默认 20 像素）
- **THEN** 系统发射 `visual.shake` 事件，载荷包含 `{ confidence: float }`

#### Scenario: 单方向转头不误判

- **WHEN** 用户仅朝一个方向转头（如向左看），未形成完整往复
- **THEN** 系统不发射 `visual.shake` 事件

#### Scenario: 连续摇头

- **WHEN** 用户在 2 秒内完成 2 次摇头动作
- **THEN** 系统为每次有效摇头分别发射 `visual.shake` 事件，连续摇头可被视为更高置信度的否定信号

### Requirement: 挥手检测 (Hand Wave Detection)

系统 SHALL 使用 MediaPipe Hands 的 21 个手部关键点，提取掌心中心（取关键点 0, 5, 9, 13, 17 的均值坐标），追踪掌心在画面中的水平运动。当掌心在 0.5 秒内水平位移超过阈值（默认 120 像素）时，系统 SHALL 发射 `visual.wave` 事件。该事件用于远程唤醒场景，用户无需靠近设备即可触发。

#### Scenario: 检测到挥手动作

- **WHEN** 用户手部在摄像头前水平移动，掌心中心在 0.5 秒内水平位移超过 120 像素
- **THEN** 系统发射 `visual.wave` 事件，载荷包含 `{ confidence: float, palm_velocity: float, direction: "left_to_right" | "right_to_left" }`

#### Scenario: 手部静止不误判

- **WHEN** 用户手部在摄像头前方保持静止，掌心水平位移未超过阈值
- **THEN** 系统不发射 `visual.wave` 事件

#### Scenario: 多人挥手

- **WHEN** 摄像头视野中出现多只手，其中至少一只手满足挥手条件
- **THEN** 系统为满足条件的每只手掌分别发射 `visual.wave` 事件，事件中附加 `hand_id` 字段以区分不同手部

### Requirement: 视觉事件集成至触发融合逻辑

系统 SHALL 将视觉意图事件（gaze、nod、shake、wave）接入触发融合逻辑层，与语音事件（wake word、voice activity）共同参与意图决策。当视线检测（gaze）与语音活动或唤醒词在 500ms 窗口内同时发生时，系统 SHALL 绕过唤醒词要求，直接从 Idle 状态进入 Aware 或 Chat 状态。

#### Scenario: Gaze + 语音活动绕过唤醒词

- **WHEN** 系统处于 Idle 状态，收到 `visual.gaze_detected` 事件后的 500ms 内检测到语音活动（voice_activity）
- **THEN** 触发融合逻辑判断为"高置信度交互意图"，系统直接进入 Chat 状态，无需用户说出唤醒词

#### Scenario: 仅视觉事件无语音不触发交互

- **WHEN** 系统收到 `visual.gaze_detected` 或 `visual.wave` 事件，但在后续 2 秒窗口内无任何语音活动或唤醒词
- **THEN** 系统保持当前状态不变，视觉事件仅记录日志，不触发状态转换

#### Scenario: Nod/Shake 事件增强交互上下文

- **WHEN** 系统处于 Chat 状态，收到 `visual.nod` 事件
- **THEN** 该事件被注入对话上下文，作为用户对当前问题的肯定应答信号，与语音"是"等效处理

#### Scenario: 多视觉事件优先级

- **WHEN** 同一帧中多个视觉事件同时触发（如 gaze + nod）
- **THEN** 触发融合逻辑按优先级排序处理：shake > nod > gaze > wave。高优先级事件优先消费，低优先级事件在当前帧被抑制

### Requirement: 视觉管线性能

系统 SHALL 保证视觉意图管线的各阶段推理耗时满足以下基准：MediaPipe Face Mesh 推理 < 20ms/帧，视线/点头/摇头分类 < 5ms/帧，挥手检测 < 5ms/帧，整条视觉管线总延迟 < 30ms/帧。

#### Scenario: Face Mesh 推理性能达标

- **WHEN** 系统在 CPU 环境下对 640x480 RGB 帧运行 MediaPipe Face Mesh
- **THEN** 单帧推理耗时 < 20ms

#### Scenario: 分类器组合性能达标

- **WHEN** 系统对同一帧并发运行视线、点头、摇头、挥手四种分类器
- **THEN** 四种分类器累计耗时 < 10ms，整条视觉管线（从帧输入到事件输出）总延迟 < 30ms

#### Scenario: 长时间运行时无内存泄漏

- **WHEN** 系统连续运行视觉意图管线 1 小时（以 10fps 计，约 36000 帧）
- **THEN** 内存增长 < 20MB，无持续增长趋势
