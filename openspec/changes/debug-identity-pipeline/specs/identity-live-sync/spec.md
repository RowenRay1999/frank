# 身份识别实时同步 (Identity Live Sync)

## ADDED Requirements

### Requirement: 身份确认事件驱动面板刷新

当融合引擎确认身份后，前端 SHALL 自动刷新身份面板的人物列表（已识别成员 + 待识别访客），确保面板展示包含最新的识别统计信息（`recognition_confidence`、`last_recognized_at`、`last_active_at`）和任何新发现或更新的未标识访客记录。

#### Scenario: 身份确认后面板自动刷新

- **WHEN** 融合引擎推送 `identity.confirmed` 事件，身份面板已打开
- **THEN** 前端在更新顶栏头像/名称后，主动发送 `member.list` 和 `member.pending` 请求，并在收到响应后重新渲染身份面板人物列表

#### Scenario: 身份确认时面板未打开

- **WHEN** 融合引擎推送 `identity.confirmed` 事件，但身份面板当前未打开（`PanelManager.isOpen(identityPanel) === false`）
- **THEN** 前端更新顶栏头像/名称，但不发送 `member.list` 和 `member.pending` 请求（避免无谓的 WebSocket 通信）

### Requirement: 未标识访客自动发现事件驱动面板刷新

当融合引擎自动发现新的未标识访客或更新已有未标识访客记录时，前端 MUST 通过 `identity.unknown` 事件获得通知，并在身份面板已打开时自动刷新待识别访客列表。

#### Scenario: 新访客自动发现后面板刷新

- **WHEN** 融合引擎在 `_check_auto_discovery` 中成功创建新的未标识人物记录（如"访客-005"），并广播 `identity.unknown` 事件携带 `{person_id, display_name, is_new: true, appearance_count: 1}`
- **THEN** 前端收到事件后，若身份面板已打开，发送 `member.pending` 请求刷新待识别列表

#### Scenario: 已有未标识访客再次出现后面板刷新

- **WHEN** 融合引擎在 `_check_auto_discovery` 中匹配到已有未标识人物（如"访客-003"），更新其 `appearance_count`，并广播 `identity.unknown` 事件携带 `{person_id, display_name, is_new: false, appearance_count: 3}`
- **THEN** 前端收到事件后，若身份面板已打开，发送 `member.pending` 请求刷新待识别列表

### Requirement: 面板人物列表渲染修复

前端 `renderPersonList` 函数 MUST 使用正确的数据库字段名映射：未标识人物的显示名称取值路径为 `p.display_name`（与后端 `unidentified` 表的 `display_name` 列一致），而非 `p.serial_name`（不存在的字段）。

#### Scenario: 未标识访客显示正确的序列名称

- **WHEN** 后端返回的未标识人物记录包含 `display_name: "访客-001"`
- **THEN** 前端身份面板中该人物条目显示"访客-001"，而非回退到自动生成的临时名称

#### Scenario: 未标识访客 display_name 为 NULL 时使用回退

- **WHEN** 后端返回的未标识人物记录的 `display_name` 为 `null` 或 `undefined`
- **THEN** 前端使用回退名称 `访客_${id.substring(0,4)}` 显示
