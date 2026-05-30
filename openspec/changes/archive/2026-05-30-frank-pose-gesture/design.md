## Context

Phase 5 实现设计文档 `2026-05-30-frank-05-member-biometrics.md` 第 12 节预留的 PoseModule 接口。当前系统已有：
- Phase 3: MediaPipe Face Mesh (468 landmarks) + Hands (21 landmarks) 用于视觉意图（注视、点头、摇头、挥手）
- Phase 1-2: CameraPipeline 采集 640×480 RGB 帧，InsightFace/MediaPipe 人脸检测
- 帧捕获以自适应帧率运行（Idle=1fps, Aware=5fps, Auth/Chat=10fps）

Phase 5 在已有基础上扩展：从当前 Face-level 手势 → 完整的 Hand-level + Body-level 姿态识别。

## Goals / Non-Goals

**Goals:**
- 实现 PoseModule：利用 MediaPipe Pose (BlazePose) 提取 33 身体关节点、MediaPipe Hands (21 关节点) 完整提取双手关键点
- 实现规则引擎手势分类器：识别 4 种预定义手势 (raise_hand, point, wave, come_closer)
- 实现 DTW 自定义手势注册与匹配
- 实现手势动作槽 pub-sub 系统：手势 → 系统动作
- 集成到 CameraPipeline：复用同一帧，联合人脸+姿态+手势提取
- 手势作为第 5 种输入模态接入对话编排器和状态机

**Non-Goals:**
- 全身骨骼追踪/动作捕捉
- 手语识别
- 实时手势到文本连续输入
- 3D 姿态重建
- 姿态数据网络传输（所有数据本地处理）

## Decisions

### D1: 规则引擎 vs 深度学习手势分类器

**选择**: 规则引擎（关键点几何关系 + 时序模式匹配）

**理由**:
- 预定义手势（举手/指向/挥手/走近）可通过几何关系可靠识别，无需训练数据
- 深度学习模型（1D-CNN/LSTM）带来额外依赖和推理开销，4 种手势不值得
- 规则引擎可解释、可调试、可调整阈值
- DTW 自定义手势已提供序列匹配能力，覆盖个性化需求

**alternatives**: 1D-CNN 训练自定义手势模型 → 需要训练数据，过拟合风险，维护成本高

### D2: 复用 camera_pipeline 帧 vs 独立采集循环

**选择**: 在 CameraPipeline 中扩展现有帧捕获循环，增加 Pose/Hands 初始化

**理由**:
- 单帧 RGB 可同时输入 Face Mesh + Pose + Hands，避免多次解码
- 减少 CPU/GPU 上下文切换
- 姿态提取可与人脸检测共享 FPS 策略（Aware=5fps 足够姿态检测）
- MediaPipe 三合一会话已通过 GPU 委托优化

**alternatives**: 独立线程跑 Pose 模块 → 额外帧拷贝、同步复杂性、没必要

### D3: DTW vs HMM vs 神经网络用于自定义手势

**选择**: DTW (Dynamic Time Warping) + 归一化关键点距离特征

**理由**:
- DTW 对小样本（用户演示 1-3 次）友好，无需训练
- 计算成本可控：单次 DTW O(n²)，序列长度 < 90 帧 (3s @ 30fps)
- 已有成熟实现（fastdtw 或手写优化版本）
- 用户自定义手势数量有限（预计 < 20），线性搜索足够

**alternatives**: HMM → 需要多个训练样本，对小样本不友好；Reservoir Computing → 过度工程

### D4: 手势触发槽架构

**选择**: 内存 pub-sub 字典，`dict[gesture_type, list[Callback]]`

**理由**:
- 手势 → 系统动作的映射是配置性质的，不需要持久化队列
- 回调在 asyncio 事件循环中执行，与现有架构一致
- 支持多订阅者（如：举手 → 暂停对话 + 降低音量）
- 与现有 `_on_*` 回调模式一致

### D5: 自定义手势存储

**选择**: SQLite `custom_gestures` 表，存储关键点序列 JSON

**理由**:
- 与已有 members 表和 skill_preferences 表在同一数据库
- JSON 存储灵活，支持不同长度序列
- 成员关联：每个自定义手势绑定到 member_id

## Risks / Trade-offs

| Risk | Impact | Mitigation |
|------|--------|------------|
| MediaPipe Pose 增加 CPU 负载 | Aware 状态 5fps 下增加 ~15ms/帧 | 仅在 Auth/Chat 状态运行 Pose，Idle/Aware 仅运行 Hands（已在运行） |
| DTW 在线匹配延迟 | 3s 序列 DTW ~5ms，20 个手势 ~100ms | 限制注册手势数 ≤ 50，使用 fastdtw 近似算法 |
| 低光/遮挡影响姿态检测 | 关键点置信度下降 | 门控：仅使用 confidence > 0.5 的关键点，低于阈值的帧丢弃 |
| 手势误触发（类似"扰民"） | 用户无关动作被识别为手势 | 组合门控：人脸存在 + 关键点置信度 + 时序连贯性 + 防抖 (debounce 2s) |
| 与现有 Face-level 手势重叠 | wave 在 Phase 3 (手部) 和 Phase 5 (全身) 都可检测 | Phase 5 wave 使用 Pose 手腕关键点（更大范围移动），Phase 3 保留手掌级 wave |

## Migration Plan

1. 部署：新增文件 + 修改 camera_pipeline.py 和 main.py
2. 回滚：Pose 模块可配置禁用（`config/frank.yaml` 中 `pose.enabled: false`），禁用后系统回归 Phase 4 行为
3. 数据库迁移：新增 `custom_gestures` 表，版本号 schema_version = 2
4. 无破坏性变更：所有现有 API 和事件保持不变

## Open Questions

- 是否需要支持双手独立手势？（当前设计：双手关节点同时提取，但分类基于整体）
- 走近/离开检测是否需要距离估计？（当前设计：基于人脸 bbox 大小变化 + 身体关键点 Y 位移）
