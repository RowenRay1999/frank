# 身份融合引擎 (Identity Fusion) — Delta Spec

## MODIFIED Requirements

### Requirement: 未标识访客自动发现

当融合引擎判定当前身份为 UNKNOWN（两模态均低于匹配阈值）且有有效人脸嵌入时，引擎 SHALL 自动检查该人脸是否匹配已知的未标识访客。如果匹配到已有未标识记录（余弦相似度 >= 0.6），则更新该记录的出现次数和最后活跃时间。如果 30 秒内未匹配到同一人脸，则自动创建新的未标识人物记录（命名为"访客-NNN"），并将人脸嵌入存储到 `unidentified` 表中。系统 MUST 通过 `identity.unknown` 事件将未标识人物的基本信息推送给前端展示。

#### Scenario: 新人首次出现触发自动发现

- **WHEN** 一个未注册的人站在摄像头前，人脸嵌入与所有已注册成员和已有未标识记录的相似度均低于阈值（0.6），且距离上次同嵌入哈希的冷却时间已超过 30 秒
- **THEN** 融合引擎调用 `add_unidentified` 创建新记录（如"访客-001"），人脸嵌入存储到数据库，并通过 `on_identity_unknown` 回调推送事件，事件载荷包含 `{person_id, display_name: '访客-001', is_new: true, appearance_count: 1}`

#### Scenario: 已发现的未标识访客再次出现

- **WHEN** 之前已被自动发现的未标识访客（如"访客-003"）再次出现在摄像头前，人脸嵌入与 unidentified 表中记录的相似度 >= 0.6
- **THEN** 融合引擎调用 `update_unidentified` 更新该记录的出现次数和最后活跃时间，并通过 `on_identity_unknown` 回调推送事件，事件载荷包含 `{person_id, display_name: '访客-003', appearance_count: 3, is_new: false}`

#### Scenario: 同一访客在 30 秒冷却期内不重复创建

- **WHEN** 同一人脸嵌入在 30 秒内多次被处理（例如摄像头连续帧），且该嵌入对应的访客刚刚被创建
- **THEN** 融合引擎跳过自动发现逻辑，不创建重复记录，不更新计数（避免同一短时间窗口内重复计数）

#### Scenario: 两模态均有效但 UNKNOWN 时仍触发自动发现

- **WHEN** 人脸置信度 >= 0.5 且声纹置信度 >= 0.5，但两者均不匹配任何已注册成员
- **THEN** 融合引擎仍执行自动发现（与单模态 UNKNOWN 逻辑相同），因该访客尚未注册

### Requirement: 推送身份结果事件

融合引擎 MUST 在每个决策周期结束后，向状态机及上层应用推送 `identity_result` 事件，事件载荷中包含以下字段：`person_id`（成员唯一标识）、`display_name`（显示名称）、`role`（角色等级）、`confidence`（综合置信度）、`source`（决策来源，枚举值 `face` / `voice` / `both`）、`is_tentative`（是否为暂定状态，布尔值）。

此外，当融合引擎触发 UNKNOWN 状态且完成自动发现检查后，`identity.unknown` 事件载荷 MUST 包含自动发现结果：`auto_discovered` 字段（对象或 null），其子字段包括 `person_id`、`display_name`、`is_new`、`appearance_count`。

#### Scenario: 双模态融合确认后推送事件

- **WHEN** 融合引擎通过双高置信度确认身份为 Alice（角色 Owner，置信度 0.90，来源为 both，非暂定）
- **THEN** 引擎推送的 `identity_result` 事件包含：`person_id: "usr_alice_001"`，`display_name: "Alice"`，`role: "owner"`，`confidence: 0.90`，`source: "both"`，`is_tentative: false`

#### Scenario: 单模态暂定确认后推送事件

- **WHEN** 融合引擎仅通过人脸高置信度暂定身份为 Bob（角色 Adult，置信度 0.88，来源为 face，状态为暂定）
- **THEN** 引擎推送的 `identity_result` 事件包含：`person_id: "usr_bob_002"`，`display_name: "Bob"`，`role: "adult"`，`confidence: 0.88`，`source: "face"`，`is_tentative: true`

#### Scenario: UNKNOWN 状态携带自动发现结果

- **WHEN** 融合引擎判定当前身份为 UNKNOWN，`_check_auto_discovery` 成功创建新的未标识访客"访客-007"
- **THEN** 引擎推送的 `identity.unknown` 事件载荷包含 `auto_discovered: {person_id: "xxx", display_name: "访客-007", is_new: true, appearance_count: 1}`
