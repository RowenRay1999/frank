# pose-detection — 身体姿态提取

## ADDED Requirements

### Requirement: MediaPipe Pose 初始化
系统 SHALL 初始化 MediaPipe Pose (BlazePose) 模型，提取 33 个身体关键点 (x, y, z, visibility)。模型 SHALL 在 Auth/Chat 状态下激活，Idle/Aware 状态下不运行以节省 CPU。

#### Scenario: Pose 模型加载成功
- **WHEN** 系统启动且 `config/frank.yaml` 中 `pose.enabled` 为 `true`
- **THEN** MediaPipe Pose 模型异步加载，就绪后设置 `ready` 标志为 `true`，日志输出 "Pose module ready"

#### Scenario: Pose 模型加载失败降级
- **WHEN** MediaPipe Pose 模型加载失败（文件缺失、内存不足）
- **THEN** 系统记录 WARNING 日志，`ready` 标志保持 `false`，不影响其他模块运行

#### Scenario: 低功耗状态下不运行 Pose
- **WHEN** 系统处于 Idle 或 Aware 状态
- **THEN** Pose 提取不执行，减少 CPU 占用

### Requirement: 关键点提取
系统 SHALL 对每帧 RGB 图像运行 MediaPipe Pose，输出 33 个身体关键点的归一化坐标 (x, y, z) 和可见度 (visibility)。关键点 SHALL 以 PoseFrame 数据结构封装。

#### Scenario: 检测到完整人体
- **WHEN** 帧中包含完整人体且 MediaPipe Pose 成功检测
- **THEN** 返回 PoseFrame，包含 33 个关键点的 `(x, y, z, visibility)` 四元组，及帧时间戳

#### Scenario: 未检测到人体
- **WHEN** 帧中无人体或遮挡严重
- **THEN** `extract_pose()` 返回 `None`，不产生事件

#### Scenario: 部分关键点可见
- **WHEN** 人体部分被遮挡（如下半身被桌子遮挡）
- **THEN** 返回完整 33 关键点数组，被遮挡关键点的 visibility < 0.5

### Requirement: 双手关键点提取
系统 SHALL 扩展当前 MediaPipe Hands(用于 Phase 3 视觉意图的挥手检测)为完整 21 关键点提取，包含左手和右手的独立关键点。双手关键点 SHALL 附加到 PoseFrame 中。

#### Scenario: 双手同时检测
- **WHEN** 帧中可见双手且 MediaPipe Hands 成功检测
- **THEN** PoseFrame 中 `left_hand_landmarks` 和 `right_hand_landmarks` 均为 (21, 3) 数组

#### Scenario: 仅单手可见
- **WHEN** 帧中仅可见一只手
- **THEN** PoseFrame 中对应手的 landmarks 为有效数组，另一手为 `None`

#### Scenario: 双手均不可见
- **WHEN** 帧中无手部
- **THEN** PoseFrame 中双手 landmarks 均为 `None`

### Requirement: Pose 配置
系统 SHALL 通过 `config/frank.yaml` 的 `pose` 节配置姿态检测参数。

#### Scenario: 默认配置
- **WHEN** 未在配置文件中指定 `pose` 节
- **THEN** 系统使用默认值：`enabled: true`, `min_detection_confidence: 0.5`, `min_tracking_confidence: 0.5`, `model_complexity: 1`

#### Scenario: 禁用 Pose 模块
- **WHEN** 用户设置 `pose.enabled: false`
- **THEN** Pose 模块不初始化，不消耗额外 CPU/GPU 资源

### Requirement: 内存与性能
系统 SHALL 保证 Pose 提取单帧延迟 < 30ms (CPU)，不与已有 Face Mesh/Hands 产生显著叠加开销。

#### Scenario: 联合推理性能
- **WHEN** 单帧同时运行 Face Mesh + Pose + Hands 提取
- **THEN** 总延迟 < 80ms (CPU 环境，640×480 RGB 帧)

#### Scenario: 资源释放
- **WHEN** 系统关闭或 Pose 模块被停止
- **THEN** MediaPipe Pose 实例被正确释放，GPU 资源回收
