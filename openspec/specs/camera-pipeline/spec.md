# Camera Pipeline 相机流水线

## ADDED Requirements

### Requirement: 摄像头设备枚举
系统 SHALL 在启动时枚举所有可用摄像头设备，并将设备列表通过 `camera.devices` 响应推送给 Electron。

#### Scenario: 成功枚举设备列表
- **WHEN** Python 服务启动完成
- **THEN** 系统枚举所有可用摄像头，返回 `camera.devices` 响应，格式为 `[{ id: int, name: string, resolutions: [{width, height, fps}] }]`，同时使用配置中指定的默认设备

#### Scenario: 无可用摄像头
- **WHEN** 系统启动时未检测到任何摄像头设备
- **THEN** 返回空数组 `[]` 作为设备列表，并触发 `camera.error` 错误事件

### Requirement: 摄像头启动与停止
系统 SHALL 响应 Electron 的 `camera.start` 和 `camera.stop` 命令，分别控制摄像头打开与释放。

#### Scenario: 启动摄像头成功
- **WHEN** Electron 发送 `camera.start` 命令，且指定设备可用
- **THEN** Python 使用配置的参数打开摄像头，启动帧捕获循环，开始向 Electron 推送检测事件

#### Scenario: 停止摄像头成功
- **WHEN** Electron 发送 `camera.stop` 命令
- **THEN** Python 释放摄像头资源，停止帧捕获循环

#### Scenario: 应用退出时自动释放
- **WHEN** 应用退出（无论正常退出还是异常崩溃）
- **THEN** 系统确保摄像头资源被释放，不会占用设备

### Requirement: 帧捕获循环
系统 SHALL 根据当前状态自适应调整帧率，使用 OpenCV VideoCapture 捕获 640x480 RGB 格式的帧。

#### Scenario: 空闲状态低帧率
- **WHEN** 系统处于 `Idle` 状态
- **THEN** 帧捕获频率为 1fps，以降低 CPU 和功耗开销

#### Scenario: 感知状态中等帧率
- **WHEN** 系统处于 `Aware` 状态
- **THEN** 帧捕获频率提升至 5fps，以满足人脸检测的实时性需求

#### Scenario: 认证/对话状态高帧率
- **WHEN** 系统处于 `Auth` 或 `Chat` 状态
- **THEN** 帧捕获频率提升至 10fps，以支持高频交互场景

#### Scenario: 帧格式与分辨率
- **WHEN** 摄像头启动并开始捕获帧
- **THEN** 每帧格式为 RGB，分辨率为 640x480，使用 OpenCV VideoCapture 实现

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

### Requirement: 错误处理
系统 SHALL 在摄像头相关错误发生时推送 `camera.error` 事件，包含错误码、可恢复标志和用户友好建议。

#### Scenario: 摄像头未找到
- **WHEN** 启动摄像头时指定的设备不存在
- **THEN** 系统推送 `camera.error` 事件，`code` 为 `"CAM_NOT_FOUND"`，`recoverable` 为 `true`，suggestion 为 `"请检查摄像头是否已连接"`

#### Scenario: 摄像头权限被拒
- **WHEN** 操作系统拒绝应用程序的摄像头访问权限
- **THEN** 系统推送 `camera.error` 事件，`code` 为 `"CAM_PERMISSION_DENIED"`，`recoverable` 为 `true`，suggestion 为 `"请在系统设置中允许弗兰克访问摄像头"`

#### Scenario: 摄像头运行中断开
- **WHEN** 摄像头在运行中被物理断开
- **THEN** 系统推送 `camera.error` 事件，`code` 为 `"CAM_DISCONNECTED"`，`recoverable` 为 `true`，suggestion 为 `"摄像头连接已断开，请重新连接后重试"`

### Requirement: 设备热插拔
系统 SHALL 实时监控摄像头设备列表变化，在设备插入或拔出时做出相应处理。

#### Scenario: 新摄像头接入
- **WHEN** 系统运行期间检测到新的摄像头设备接入
- **THEN** 系统推送 `camera.device_added` 事件，包含新设备的 `{ id, name, resolutions }` 信息

#### Scenario: 活动摄像头断开自动切换
- **WHEN** 当前正在使用的摄像头被拔出
- **THEN** 系统推送 `camera.error` 事件（`code: "CAM_DISCONNECTED"`），并自动回退到下一个可用摄像头；若无可用摄像头则进入降级模式

#### Scenario: 降级模式运行
- **WHEN** 所有摄像头均不可用，系统进入降级模式
- **THEN** 所有依赖人脸检测的功能暂停，直到有摄像头重新可用

### Requirement: 性能与配置
系统 SHALL 保证单帧人脸检测延迟小于 50ms（CPU 环境），检测置信度阈值可配置，默认值为 0.7。

#### Scenario: 检测延迟达标
- **WHEN** 在 CPU 环境下对 640x480 RGB 帧进行人脸检测
- **THEN** 单帧检测延迟 < 50ms

#### Scenario: 置信度阈值配置
- **WHEN** 检测到的人脸置信度低于配置的阈值（默认 0.7）
- **THEN** 该人脸不被纳入有效检测结果，不会触发 `camera.face_detected` 事件

#### Scenario: 阈值动态调整
- **WHEN** 用户通过配置修改置信度阈值
- **THEN** 系统在下一次检测时立即生效，无需重启摄像头或应用

### Requirement: 人脸嵌入提取

在 MediaPipe/SCRFD 检测到人脸后，系统 SHALL 对每个有效人脸 ROI 运行 InsightFace ArcFace 编码器，提取 512 维 L2 归一化的人脸嵌入向量，嵌入向量与检测结果一并输出。

#### Scenario: 提取嵌入成功

- **WHEN** 检测到有效人脸（通过嵌入质量门控），且 InsightFace ArcFace 编码器加载正常
- **THEN** 系统对检测框（bbox）裁剪的人脸区域运行 ArcFace 编码器，输出 512 维 L2 归一化浮点向量，该向量作为 `embedding` 字段附加到对应的人脸检测结果中

#### Scenario: 嵌入提取失败

- **WHEN** InsightFace ArcFace 编码器推理失败（如输入 ROI 无效、模型异常）
- **THEN** 该人脸的 `embedding` 字段置为 `null`，系统推送 `camera.error` 事件，`code` 为 `"EMBEDDING_FAILED"`，`recoverable` 为 `true`，suggestion 为 `"人脸嵌入提取失败，将降级为仅检测模式"`

### Requirement: InsightFace buffalo_l 作为主检测器

系统 SHALL 以 InsightFace buffalo_l 模型作为首选的人脸检测与识别引擎，MediaPipe Face Detector 作为后备方案。当 InsightFace 初始化或运行时发生不可恢复错误时，系统自动回退到 MediaPipe。

#### Scenario: InsightFace 加载成功

- **WHEN** 系统启动时加载 InsightFace buffalo_l 模型成功
- **THEN** 人脸检测使用 InsightFace SCRFD 检测器，识别使用 ArcFace 编码器；MediaPipe 模型保持加载但不激活

#### Scenario: InsightFace 加载失败回退

- **WHEN** InsightFace buffalo_l 模型文件缺失、版本不匹配或初始化异常
- **THEN** 系统自动回退到 MediaPipe Face Detector（短距离模型），同时推送 `camera.error` 事件，`code` 为 `"INSIGHTFACE_LOAD_FAILED"`，`recoverable` 为 `false`，suggestion 为 `"InsightFace 模型加载失败，已回退至 MediaPipe 检测模式"`

#### Scenario: InsightFace 运行时异常回退

- **WHEN** InsightFace 在运行过程中抛出不可恢复异常
- **THEN** 系统自动切换至 MediaPipe 检测模式，当前帧使用 MediaPipe 重新检测，并推送 `camera.error` 事件，`code` 为 `"INSIGHTFACE_RUNTIME_ERROR"`，`recoverable` 为 `false`，suggestion 为 `"InsightFace 运行时异常，已回退至 MediaPipe 检测模式"`

#### Scenario: 模型状态报告

- **WHEN** Electron 查询当前检测器状态
- **THEN** 系统返回 `camera.detector_status` 响应，包含 `{ active_detector: "insightface" | "mediapipe", embedding_available: bool }`

### Requirement: 嵌入质量门控

系统 SHALL 仅对同时满足以下条件的人脸提取嵌入向量：人脸置信度 > 0.7、人脸区域 >= 80x80 像素、正面角度偏差 < 30 度（基于人脸关键点估计）。低于阈值的人脸仅产生检测事件，不产生嵌入向量。

#### Scenario: 满足质量门控

- **WHEN** 检测到的人脸满足全部三项条件：置信度 > 0.7、人脸区域宽度 >= 80px 且高度 >= 80px、估计偏转角（yaw）< 30 度
- **THEN** 系统对该人脸提取 512 维嵌入向量，附加到检测结果中

#### Scenario: 置信度不足

- **WHEN** 检测到的人脸置信度 <= 0.7
- **THEN** 该人脸被标记为低质量，检测结果中 `embedding` 字段为 `null`，不触发嵌入提取

#### Scenario: 人脸区域过小

- **WHEN** 人脸区域宽度 < 80px 或高度 < 80px
- **THEN** 该人脸被标记为低质量，检测结果中 `embedding` 字段为 `null`，不触发嵌入提取

#### Scenario: 角度偏差过大

- **WHEN** 基于两眼及鼻尖关键点估计的偏转角（yaw）>= 30 度
- **THEN** 该人脸被标记为低质量，检测结果中 `embedding` 字段为 `null`，不触发嵌入提取

#### Scenario: 质量门控阈值可配置

- **WHEN** 用户通过配置修改嵌入质量门控参数（confidence_min、face_size_min、angle_max）
- **THEN** 系统在下一次检测时立即生效，无需重启摄像头或应用

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

---

## ADDED Requirements (Phase 5)

### Requirement: 姿态/手势帧提取回调
CameraPipeline SHALL 新增 `set_on_pose_frame` 回调注册接口，在每帧人脸检测完成后提取姿态和手部关键点，并通过回调传递给 PoseModule。

#### Scenario: 姿态帧回调注册
- **WHEN** PoseModule 调用 `camera_pipeline.set_on_pose_frame(callback)`
- **THEN** 回调被存储，后续每帧人脸检测完成后调用 `callback(frame_rgb, frame_w, frame_h)`

#### Scenario: 姿态帧回调触发
- **WHEN** 摄像头捕获一帧且人脸检测完成
- **AND** 状态为 Auth 或 Chat（高帧率模式）
- **THEN** 回调被调用，传入当前帧 RGB 数据和尺寸

#### Scenario: 低功耗状态跳过姿态提取
- **WHEN** 系统处于 Idle 状态（1fps）
- **THEN** 姿态帧回调不被调用，节省 CPU 资源

### Requirement: 姿态与视觉意图联合处理
CameraPipeline SHALL 在帧处理中支持同时运行人脸检测 + Face Mesh + Pose + Hands 的联合管线，各模块共享同一帧 RGB 数据避免重复解码。

#### Scenario: 联合管线输出
- **WHEN** 系统处于 Chat 状态（10fps）
- **THEN** 单帧依次经过：InsightFace 人脸检测 → 嵌入提取 → Pose 关键点提取 → Hands 关键点提取，所有结果在同一帧循环中处理

#### Scenario: 模块降级不影响其他模块
- **WHEN** Pose 模块初始化失败（MediaPipe Pose 不可用）
- **THEN** 人脸检测和 Face Mesh 仍正常运行，不影响身份识别和视觉意图
