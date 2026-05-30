## Why

Frank 目前支持 4 种输入模态（声音强度、唤醒词、免唤醒指令、视觉意图），但在免提/静音场景下交互手段受限。肢体姿态和手势是自然的补充交互通道——举手暂停、挥手切歌、走近激活——且与已有 Face Mesh/Hands 同框架（MediaPipe），无需引入新依赖，计算增量可控。

## What Changes

- 实现设计文档 `2026-05-30-frank-05-member-biometrics.md` 第 12 节预留的 PoseModule 接口
- Body-level: MediaPipe Pose (BlazePose) 提取 33 关节点 → 识别举手、走近/离开、坐下/站立
- Hand-level: MediaPipe Hands 扩展至 21 关节点完整提取 → 识别手指数字、指向、手掌手势
- 规则引擎 + DTW 时序对齐实现手势分类和自定义手势注册
- 手势触发槽（pub-sub）：举手→暂停对话、挥手→切歌、走近→激活、自定义→快捷指令
- 自定义手势存储到 SQLite，支持 DTW 匹配
- 与 camera_pipeline 融合，复用同一帧进行人脸+姿态+手势联合提取
- 手势作为第 5 种输入模态接入对话编排器

## Capabilities

### New Capabilities
- `pose-detection`: 身体姿态提取 — MediaPipe Pose (BlazePose) 33 关键点，每帧输出 PoseFrame
- `gesture-recognition`: 手势分类 — 规则引擎识别预定义手势（raise_hand / point / wave / come_closer）+ DTW 自定义手势匹配
- `gesture-actions`: 手势动作槽 — pub-sub 模式绑定手势到系统动作（暂停对话、切换技能、执行快捷指令），支持用户注册自定义手势

### Modified Capabilities
- `camera-pipeline`: 增加姿态/手势提取回调（与已有 Face Mesh/Hands 并行），复用同一帧
- `state-machine`: 增加 gesture_detected 事件，支持手势驱动的状态转换
- `ui-shell`: Electron 渲染器新增手势事件监听和反馈提示

## Impact

- **src/python/modules/pose/**: 新增姿态/手势模块目录
- **src/python/modules/camera/camera_pipeline.py**: 添加 Pose/Hands 初始化与回调
- **src/python/server/main.py**: 添加 PoseModule 初始化和事件路由
- **src/python/shared/database.py**: 添加 custom_gestures 表
- **src/electron/main/main.js**: 添加 gesture.* 消息转发
- **src/electron/renderer/app.js**: 添加手势事件 UI 反馈
- **config/frank.yaml**: 添加 pose/gesture 配置节
- 依赖: mediapipe (已有，无需新增)
