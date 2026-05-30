# Camera Pipeline 相机流水线

## ADDED Requirements

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

## MODIFIED Requirements

### Requirement: 人脸检测

系统 SHALL 以 InsightFace SCRFD 为优先级最高的检测器，对每帧运行人脸检测；若 InsightFace 不可用则回退至 MediaPipe Face Detector（短距离模型）。无论使用何种检测器，返回统一的检测结果数组。

#### Scenario: 检测到人脸

- **WHEN** 捕获的帧中包含人脸
- **THEN** 检测结果包含 faces 数组，每个元素包含：`{ bbox: {x, y, width, height}, confidence: float, landmarks: [{x, y, z}], embedding: [512 维浮点数组] | null }`
  - `embedding` 字段在嵌入质量门控通过时包含 512 维 L2 归一化向量，否则为 `null`

#### Scenario: 无人脸

- **WHEN** 捕获的帧中无人脸
- **THEN** 检测结果返回空数组 `[]`

#### Scenario: 检测器自动切换

- **WHEN** InsightFace SCRFD 初始化失败或运行时异常
- **THEN** 系统自动回退至 MediaPipe Face Detector，检测结果格式保持一致；`embedding` 字段在 MediaPipe 模式下始终为 `null`
