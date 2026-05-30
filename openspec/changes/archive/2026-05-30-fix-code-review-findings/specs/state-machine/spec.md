## MODIFIED Requirements

### Requirement: 状态转换

系统必须按照定义的转换规则在四个状态之间流转，每种转换由特定触发条件驱动。Aware 到 Auth 的转换现由身份融合引擎驱动，不再依赖固定 2s 人脸持续检测。**唤醒词 "Hey Frank" 被检测到时，系统 MUST 从任意状态（Idle、Aware、Auth、Chat）转入 Chat 状态**，而非仅从 Auth/Chat 状态。

#### 转换规则表

| 源状态 | 目标状态 | 触发条件 | 说明 |
|--------|----------|----------|------|
| Idle | Aware | 人脸检测到（MediaPipe 返回边界框）OR 语音活动检测到（Silero VAD 触发） | 任一条件满足即转换 |
| Idle | Chat | 唤醒词 "Hey Frank" 被检测到 | **新增**: 免人脸直接通过语音唤醒 |
| Aware | Idle | 无人脸 AND 无语音持续 timeout_aware 秒 | 默认 30s 超时 |
| Aware | Auth | 身份融合引擎输出 confirmed identity，融合置信度 >= 阈值（默认 0.85） | 替代 Phase 1 的 2s 连续人脸检测。身份上下文包含 { person_id, display_name, role, confidence } |
| Aware | Chat | 唤醒词 "Hey Frank" 被检测到 | **新增**: 无需等待身份确认即可唤醒 |
| Auth | Chat | 唤醒词 "Hey Frank" 被检测到 | 需精确匹配唤醒词（保持原有） |
| Chat | Auth | 最后一次响应后沉默 timeout_chat 秒 | 默认 5min |
| Chat | Auth（身份变更新流程） | 身份融合引擎在 Chat 状态下检测到 face/voice embedding 切换，emit "identity_changing" 事件，暂停对话，重新执行融合。新身份确认后，先转入 Auth(new_identity)，再由用户唤醒进入 Chat | 参见"身份变更检测"需求 |
| Auth | Idle | 无人脸持续 timeout_auth_to_idle 秒 | 默认 60s |

#### Scenario: Idle 状态下唤醒词直接进入 Chat

- **WHEN** 系统处于 Idle 状态（无人脸检测），用户说出 "Hey Frank"
- **THEN** 系统从 Idle 转入 Chat 状态，唤醒词检测器触发，对话编排器启动，身份暂为 guest

#### Scenario: Aware 状态下唤醒词进入 Chat

- **WHEN** 系统处于 Aware 状态（人脸已检测但身份尚未确认），用户说出 "Hey Frank"
- **THEN** 系统从 Aware 转入 Chat 状态，对话以当前检测到的身份上下文（如有）或 guest 身份运行
