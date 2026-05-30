# state-machine — Phase 5 手势事件

## ADDED Requirements

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
