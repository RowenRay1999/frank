## Context

Phase 1 完成了 Frank 的骨架——人脸检测（MediaPipe）、语音活动检测（Silero VAD）、唤醒词识别（OpenWakeWord）和状态机流转。但 Phase 1 的 Auth 状态是简化版：只要摄像头检测到人脸持续 2 秒就进入 Auth。系统还没有"谁是谁"的概念。Phase 2 在此基础上叠加身份识别层。

**当前代码状态**：
- 人脸检测：`camera_pipeline.py` 使用 MediaPipe Face Detector，输出 bbox + 6 landmarks，无 embedding
- 音频处理：`audio_pipeline.py` 使用 Silero VAD + OpenWakeWord，无声纹提取
- 状态机：`state_machine.py` 的 Auth 转换条件是 `face_detected && time > 2s`
- 成员管理：无，无数据库
- UI：静态欢迎语"下午好，需要我做些什么？"

**设计文档参考**：`docs/superpowers/specs/2026-05-30-frank-02-identity-recognition.md` 和 `2026-05-30-frank-05-member-biometrics.md`

## Goals / Non-Goals

**Goals:**
- 人脸 embedding 提取（InsightFace buffalo_l, 512-dim）并与人脸检测并行运行
- 声纹 embedding 提取（SpeechBrain ECAPA-TDNN, 192-dim）在 VAD 语音段上触发
- 融合决策矩阵：并行人脸+声纹置信度评分 → 决策（确认/待确认/询问/拒绝）
- 四级角色权限系统：Owner（1人）/ Adult / Child / Guest，指令优先级
- 成员数据库（SQLite）：embedding 存储、成员 CRUD、自适应更新
- 自动发现新人：检测到未知 embedding → 自动采集 → 分配"访客-NNN"序列名
- 主人注册流程：引导采集 3-5 个角度人脸 + 3 段声纹语音
- UI 升级：显示当前用户姓名+角色，成员管理面板，主人标识面板

**Non-Goals:**
- 多人同时检测与多输出路由（Phase 4）
- 云端 LLM 集成（Phase 3）
- 任务管理系统（Phase 4）
- 技能插件系统（Phase 4）
- 视觉意图识别（注视/点头/摇头）（Phase 3）
- 免唤醒指令（Phase 3）

## Decisions

### D1: 人脸识别使用 InsightFace buffalo_l 模型

**决策**：在现有 MediaPipe 检测器基础上叠加 InsightFace `buffalo_l` 模型包（含检测+识别）。实际上 InsightFace buffalo_l 自带检测器（SCRFD），可替代 MediaPipe 实现检测+识别一步完成。

**替代方案**：
- A) 保留 MediaPipe 检测 + 单独 InsightFace ArcFace 编码器 — 两个模型独立，更灵活但多一次推理
- B) 完全切换到 InsightFace buffalo_l 管道 — 检测+识别一体化，减少推理次数

**选择**：方案 B。InsightFace buffalo_l 包含 SCRFD 检测器（速度与 MediaPipe 相当）和 ArcFace 识别器。切换到 buffalo_l 可以一步得到检测框 + 512-dim embedding，减少一次模型推理。Phase 1 的 MediaPipe 检测代码保留为 fallback（如果 InsightFace 加载失败则降级回 Phase 1 行为）。

### D2: 声纹模型使用 SpeechBrain ECAPA-TDNN 预训练权重

**决策**：通过 speechbrain 库加载 `speechbrain/spkrec-ecapa-voxceleb` 预训练模型。在 VAD 检测到的语音段上运行，提取 192-dim speaker embedding。

**替代方案**：
- A) pyannote-audio — 专门的说话人识别库，但依赖更重
- B) wespeaker — 国产 SOTA，中文数据集训练，但生态不如 SpeechBrain

**选择**：SpeechBrain ECAPA-TDNN 是 VoxCeleb 基准上 SOTA，192-dim 紧凑嵌入，库成熟度最高。后续如果中文场景精度不够可考虑微调或切换到 wespeaker。

### D3: 融合决策矩阵采用加权评分制

**决策**：两路独立产生置信度分数（与已注册成员的 cosine similarity 最高分），融合模块使用规则矩阵做最终判定。

矩阵逻辑：
```
人脸 best_score > 0.7 且声纹 best_score > 0.7 → 两路同意 → 确认身份
人脸 best_score > 0.85 且声纹 < 0.7    → 人脸主导，暂确认但标记低置信
人脸 < 0.5 且声纹 best_score > 0.8     → 声纹主导，问"你是XX吗？"
两路均 < 0.5                           → 未识别，触发自动发现流程
两路指向不同人（且各自分数 > 0.7）     → 冲突，取高分者 + 主动询问确认
```

**关键**：融合引擎不只在唤醒时刻运行一次——它持续运行，每次收到新的 embedding 就更新置信度状态，形成"证据累积"效应。

### D4: SQLite 数据库设计

**决策**：使用 Python sqlite3（内置，无额外依赖）存储两份数据：
1. 成员表（members）：id, display_name, role, face_embedding (BLOB), typical_distance_cm, voice_embedding (BLOB), labeled (bool), created_at, last_active_at, appearance_count
2. 未标识人物表（unidentified）：相同结构但 labeled=false, display_name="访客-NNN"

embedding 以 numpy → bytes 序列化存入 BLOB，读取时反序列化。不存原始图片或音频。

**安全**：数据库文件存储在 `data/frank.db`（用户 AppData 等价目录），文件权限仅当前用户可读写。embedding 是不可逆特征向量，即使数据库泄露也无法还原人脸或声音。

### D5: 成员自动发现的门槛策略

**决策**：检测到未知 embedding（与所有已知成员的最大余弦相似度 < 0.5）时，不立即创建记录。需要满足：
- 同一 embedding 聚类出现 ≥ 3 次（避免单次误检测创建大量垃圾记录）
- 每次出现间隔 ≥ 30 秒（避免同一次会话重复计数）
- 人脸质量达标（正面角度偏差 < 30°，人脸区域 ≥ 80×80px）

满足条件后自动创建"访客-NNN"记录，取 3 次 embedding 的均值作为基准。

### D6: 角色权限在状态机层面路由

**决策**：状态机在 Auth 状态产出身份后，将 `role` 字段附着在状态上下文中。后续指令处理（Phase 3 LLM 集成时）根据 role 决定：
- Owner：所有指令均可执行，可打断任何人的会话
- Adult：除成员管理和系统配置外均可执行
- Child：受限指令白名单，不可打断更高级别用户
- Guest：仅基础查询

**现在 Phase 2 的实现**：角色信息随 `state.changed` 事件推送到 Electron，UI 据此显示不同的欢迎语和可用操作入口。

## Risks / Trade-offs

- **[R1] InsightFace 模型加载时间长（首次 5-15 秒）** → 异步加载，加载期间使用 Phase 1 MediaPipe 回退，加载完成后无缝切换。模型文件缓存到 `data/models/` 目录。
- **[R2] torch + speechbrain 内存占用** → ECAPA-TDNN 模型约 80MB，torch runtime ~200MB。总内存增量约 300MB，在 Electron + Python 基线 ~200MB 基础上达到 ~500MB。对于 8GB+ 内存的 Windows 设备可接受。提供"轻量模式"选项关闭声纹识别仅用人脸。
- **[R3] 冷启动无已知成员** → 首次运行时数据库为空，所有检测到的人都是"访客-NNN"。提供明确的注册引导：UI 显示"还没有注册成员，点击注册"，主人完成注册后自动合并已有的访客记录。
- **[R4] 双胞胎/相似外貌识别混淆** → 人脸 embedding 在相似外貌上区分度有限。融合矩阵中声纹权重在低人脸置信度时自动提升，利用声音差异做区分。这是已知限制，非完美方案。
- **[R5] embedding 漂移（外貌/声音变化）** → 自适应更新机制：每周用新采集的 embedding 以 0.7:0.3 权重更新基准。连续 3 天处于临界置信度（0.55-0.70）时主动提示重新注册。

## Open Questions

- Q1: 数据库文件位置？→ `data/frank.db`（项目根目录下），与配置文件同级
- Q2: embedding 归一化方式？→ L2 归一化（InsightFace 默认），cosine similarity = dot product
- Q3: 未标识人物清理策略？→ 30 天未出现自动清理，出现 ≥5 次的豁免。主人可关闭自动清理
