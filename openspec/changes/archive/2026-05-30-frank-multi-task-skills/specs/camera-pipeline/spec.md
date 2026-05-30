# Camera Pipeline 相机流水线

## MODIFIED Requirements

### Requirement: 人脸检测

系统 SHALL 以 InsightFace SCRFD 为优先级最高的检测器，对每帧运行人脸检测；若 InsightFace 不可用则回退至 MediaPipe Face Detector（短距离模型）。无论使用何种检测器，返回统一的检测结果数组。Phase 4 起，每张检测到的人脸额外携带 `track_id` 字段，用于跨帧身份追踪。

#### Scenario: 检测到人脸

- **WHEN** 捕获的帧中包含人脸
- **THEN** 检测结果包含 faces 数组，每个元素包含：`{ bbox: {x, y, width, height}, confidence: float, landmarks: [{x, y, z}], embedding: [512 维浮点数组] | null, track_id: string | null }`
  - `embedding` 字段在嵌入质量门控通过时包含 512 维 L2 归一化向量，否则为 `null`
  - `track_id` 字段在跨帧追踪模块成功匹配该人脸与已有轨迹时为对应轨迹的唯一标识符（如 `"track_0"`、`"track_1"`）；若为新出现且尚未分配轨迹的人脸则为 `null`

#### Scenario: 无人脸

- **WHEN** 捕获的帧中无人脸
- **THEN** 检测结果返回空数组 `[]`

#### Scenario: 检测器自动切换

- **WHEN** InsightFace SCRFD 初始化失败或运行时异常
- **THEN** 系统自动回退至 MediaPipe Face Detector，检测结果格式保持一致；`embedding` 字段在 MediaPipe 模式下始终为 `null`；`track_id` 在 MediaPipe 模式下同样为 `null`

### Requirement: 检测事件推送

系统 SHALL 在检测到人脸状态变化时推送 `camera.face_detected`、`camera.face_updated` 和 `camera.face_lost` 事件，并以状态适配的速率推送 `camera.frame` 事件。Phase 4 起，所有事件推送的检测数据均包含完整的 faces 数组（每张人脸携带 bbox、embedding、confidence、track_id），而非仅计数或单张人脸数据。

#### Scenario: 新人脸出现

- **WHEN** 前一帧未出现某张人脸，当前帧中该人脸被首次检测到且跨帧追踪为其分配了新的追踪 ID
- **THEN** 系统推送 `camera.face_detected` 事件，包含该张人脸的完整数据 `{ bbox, confidence, landmarks, embedding, track_id }`
  - 多人场景下，多人先后出现时各自触发独立的 `camera.face_detected` 事件（每人一条）

#### Scenario: 人脸持续追踪

- **WHEN** 已追踪的人脸在当前帧继续出现，且追踪 ID 保持不变
- **THEN** 系统推送 `camera.face_updated` 事件，包含该人脸的最新数据 `{ bbox, confidence, landmarks, embedding, track_id }`
  - `camera.face_updated` 以帧捕获频率持续推送，反映人脸位置、置信度等信息的实时变化

#### Scenario: 人脸消失

- **WHEN** 已追踪的人脸连续 N 帧（默认 N=5，可配置）未在当前帧中检测到
- **THEN** 系统推送 `camera.face_lost` 事件，包含 `{ track_id: string }`，标识离开的人脸轨迹
  - 多人场景下，不同人脸先后离开时各自触发独立的 `camera.face_lost` 事件

#### Scenario: 持续推送帧数据

- **WHEN** 帧捕获循环持续运行
- **THEN** 系统以当前状态适配的速率推送 `camera.frame` 事件，每次包含该帧的完整检测结果，faces 数组中每张人脸均带有 `track_id` 字段

## ADDED Requirements

### Requirement: 跨帧人脸追踪

系统 SHALL 基于人脸嵌入向量的余弦相似度，对连续帧中的检测结果进行跨帧匹配，为每张唯一人脸分配并维持一个稳定的追踪 ID（track_id），从而在时间维度上跟踪每个人的出现、移动和离开。

#### Scenario: 同一个人跨帧匹配

- **WHEN** 当前帧检测到一张人脸，其嵌入向量与上一帧中某张已追踪人脸的嵌入向量余弦相似度 >= 0.7（默认阈值，可配置）
- **THEN** 系统将该人脸匹配到已有轨迹，复用该轨迹的 `track_id`，并更新轨迹的最近帧时间戳和位置信息

#### Scenario: 新人人脸分配新 ID

- **WHEN** 当前帧检测到一张人脸，其嵌入向量与所有已追踪人脸的嵌入向量余弦相似度均 < 0.7
- **THEN** 系统为该人脸分配新的 `track_id`（格式 `"track_{n}"`，n 为单调递增整数），创建新轨迹并加入追踪列表

#### Scenario: 多人同时同帧追踪

- **WHEN** 当前帧检测到多张人脸（如 2 张），系统逐张计算嵌入相似度
- **THEN** 每张人脸独立匹配已有轨迹或分配新 ID，保证同一帧内不同人脸获得不同的 `track_id`

#### Scenario: 追踪丢失与释放

- **WHEN** 某条轨迹已连续 N 帧（默认 N=5，可配置）未匹配到任何检测结果
- **THEN** 系统标记该轨迹为丢失，从活跃追踪列表中移除，随后触发 `camera.face_lost` 事件
  - 释放的 `track_id` 后续可被回收复用，但同一会话期内优先使用递增新 ID 以避免混淆

#### Scenario: 嵌入相似度阈值配置

- **WHEN** 用户通过配置修改跨帧追踪的相似度阈值（默认 0.7）或丢失判定帧数（默认 5）
- **THEN** 系统在下一次跨帧匹配时立即生效，无需重启摄像头或应用

#### Scenario: 短时遮挡后恢复追踪

- **WHEN** 某条轨迹因短暂遮挡（< N 帧）暂时丢失，之后同一人脸重新出现且嵌入匹配成功
- **THEN** 系统将该人脸重新关联到原有 `track_id`，继续追踪，不产生新的 `camera.face_detected` 事件（避免重复触发）

#### Scenario: MediaPipe 模式下追踪降级

- **WHEN** 系统已回退至 MediaPipe 检测模式（无嵌入向量可用）
- **THEN** 跨帧追踪降级为基于 IOU（交并比）的空间位置追踪：仅在同帧相邻人脸框的 IOU >= 0.5 时维持相同 `track_id`，否则分配新 ID
  - IOU 模式仅保证短时帧间连续性，不具备人脸重识别能力；遮挡恢复场景可能失败
