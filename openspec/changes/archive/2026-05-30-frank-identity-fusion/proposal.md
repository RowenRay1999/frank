## Why

Phase 1 搭建了 Frank 的骨架——摄像头能检测到人脸，麦克风能检测到声音和唤醒词，状态机能流转。但它还不知道"谁是谁"。一个家庭共享设备的核心价值在于：识别出当前是爸爸、妈妈还是孩子，并据此提供个性化响应和差异化权限。Phase 2 让 Frank 从不认人的"检测器"变成识人的"管家"。

## What Changes

- 摄像头管线升级：从 MediaPipe 人脸检测扩展到 InsightFace 人脸特征提取（512-dim embedding），实现"这是谁"而非"有人吗"
- 音频管线升级：集成 SpeechBrain ECAPA-TDNN 声纹模型（192-dim embedding），在语音活动段提取说话人特征
- 新增身份融合引擎：并行接收人脸和声纹两路置信度评分，运行融合决策矩阵输出最终身份
- 新增角色权限系统：Owner（主人，仅1人）/ Adult（成人）/ Child（儿童）/ Guest（访客）四级等级，指令优先权和技能权限按等级区分
- 新增成员管理系统：自动发现新面孔/新声音（分配序列名）、主人手动注册（人脸+声纹采集）、标识面板、自适应 embedding 更新
- 新增生物特征存储：本地 SQLite 数据库存储 embedding 向量和成员元数据，不可逆、不上传、不联网
- 状态机升级：Auth 状态从 Phase 1 的"有人脸=确认"升级为"融合决策产出具体身份+等级"；支持中途人脸/声纹变更检测
- UI 升级：成员管理面板、当前用户身份显示（替换占位欢迎语为个性化问候）、角色标识

## Capabilities

### New Capabilities
- `identity-fusion`: 双模态身份融合引擎——并行人脸+声纹置信度评分、融合决策矩阵、自适应阈值、身份变更检测
- `member-management`: 成员注册（主人引导采集人脸+声纹）、自动发现未标识人物（序列命名）、标识面板、成员删除与隐私控制
- `biometric-storage`: 本地 SQLite 生物特征存储——embedding 读写、自适应更新（加权平均）、自动清理策略、数据安全保护
- `role-permission`: 四级角色权限系统——Owner/Adult/Child/Guest，指令优先级抢占规则，技能访问控制

### Modified Capabilities
- `camera-pipeline`: 新增 InsightFace 人脸 embedding 提取层，在检测到的每张人脸上运行特征编码（本次修改为**新增**人脸识别能力，不影响已有的 MediaPipe 检测接口）
- `audio-pipeline`: 新增 SpeechBrain ECAPA-TDNN 声纹 embedding 提取层，在 VAD 语音段上运行说话人特征编码（本次修改为**新增**声纹识别能力，不影响已有的 VAD 和唤醒词接口）
- `state-machine`: Auth 状态逻辑从"人脸出现=确认"变更为"融合引擎产出身份=确认"，新增 identity_changed 和 identity_confirmed 事件，状态转换需携带身份上下文
- `ui-shell`: 欢迎卡片从静态占位变更为显示当前用户身份和角色，新增成员管理面板入口（本次修改为**扩展** UI 功能，保留原有状态指示和聊天占位）

## Impact

- **新增依赖**：insightface、speechbrain、torch、onnxruntime
- **新增数据库**：`data/frank.db`（SQLite，存储 embedding + 成员元数据）
- **新增文件**：`src/python/modules/fusion/`（融合引擎）、`src/python/modules/members/`（成员管理）、`src/python/shared/database.py`（SQLite 封装）
- **修改文件**：camera_pipeline.py（加 embedding）、audio_pipeline.py（加声纹）、state_machine.py（角色路由）、main.py（新模块注册）、main.js（新消息类型）、renderer/*（UI 扩展）
- **无破坏性变更**：所有 Phase 1 接口保持向后兼容，新能力作为扩展层叠加
