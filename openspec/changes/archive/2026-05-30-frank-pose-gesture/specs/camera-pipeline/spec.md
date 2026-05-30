# camera-pipeline — Phase 5 姿态检测集成

## ADDED Requirements

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
