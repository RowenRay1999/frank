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
系统 SHALL 对每帧运行 MediaPipe Face Detector（短距离模型），返回检测结果数组。

#### Scenario: 检测到人脸
- **WHEN** 捕获的帧中包含人脸
- **THEN** 检测结果包含 faces 数组，每个元素包含：`{ bbox: {x, y, width, height}, confidence: float, landmarks: [{x, y, z}] }`

#### Scenario: 无人脸
- **WHEN** 捕获的帧中无人脸
- **THEN** 检测结果返回空数组 `[]`

### Requirement: 检测事件推送
系统 SHALL 在检测到人脸状态变化时推送 `camera.face_detected` 和 `camera.face_lost` 事件，并以状态适配的速率推送 `camera.frame` 事件。

#### Scenario: 人脸出现
- **WHEN** 前一帧检测到 0 个人脸，当前帧检测到 >=1 个人脸
- **THEN** 系统推送 `camera.face_detected` 事件，包含人脸检测数据

#### Scenario: 人脸消失
- **WHEN** 前一帧检测到 >=1 个人脸，当前帧检测到 0 个人脸
- **THEN** 系统推送 `camera.face_lost` 事件

#### Scenario: 持续推送帧数据
- **WHEN** 帧捕获循环持续运行
- **THEN** 系统以当前状态适配的速率推送 `camera.frame` 事件，每次包含该帧的完整检测结果

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
