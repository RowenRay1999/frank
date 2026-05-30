## 1. 模型依赖与基础设施

- [x] 1.1 安装 InsightFace 及其依赖（onnxruntime, opencv-python 已存在），模型文件首次运行时自动下载到 `data/models/`
- [x] 1.2 安装 SpeechBrain + torch，加载 `speechbrain/spkrec-ecapa-voxceleb` 预训练模型
- [x] 1.3 创建 `src/python/shared/database.py`：SQLite 连接管理、schema 版本检查、迁移框架
- [x] 1.4 执行数据库初始化：创建 members 表、unidentified 表、skill_preferences 表、schema_version 表

## 2. 生物特征存储

- [x] 2.1 实现 embedding 序列化/反序列化：numpy float32 ↔ bytes (BLOB)，含 L2 归一化
- [x] 2.2 实现成员 CRUD：add_member, get_member, update_member, delete_member, list_all_members, list_unidentified
- [x] 2.3 实现余弦相似度搜索：get_by_face_embedding(query_emb, top_n) 和 get_by_voice_embedding(query_emb, top_n)，返回 [(member, score), ...]，阈值 0.5
- [x] 2.4 实现自适应 embedding 更新：update_embeddings(member_id, new_face_emb, new_voice_emb) → 加权平均，默认 0.7×旧 + 0.3×新
- [x] 2.5 添加数据安全检查：数据库文件权限限制（当前用户读写）、无网络传输、embedding 不可逆
- [x] 2.6 实现自动清理逻辑：30 天未出现的未标识人物清理，≥5 次出现豁免，清理前 3 天通知

## 3. 摄像头管线升级（InsightFace）

- [x] 3.1 集成 InsightFace buffalo_l 模型加载：异步初始化（不阻塞 Phase 1 MediaPipe 回退），加载失败降级到 Phase 1 行为
- [x] 3.2 实现 InsightFace 管道：SCRFD 检测器 + ArcFace 编码器 → 单次推理输出 bbox + 512-dim embedding
- [x] 3.3 实现 embedding 质量门控：仅在人脸置信度 > 0.7、区域 ≥ 80×80px、正面角度偏差 < 30° 时提取 embedding
- [x] 3.4 修改检测事件推送：`camera.face_detected` 包含 embedding（质量达标时），不达标仅推送 bbox
- [x] 3.5 保留 MediaPipe 作为回退：InsightFace 未就绪时使用 MediaPipe 检测（无 embedding），就绪后无缝切换

## 4. 音频管线升级（SpeechBrain 声纹）

- [x] 4.1 集成 SpeechBrain ECAPA-TDNN 模型：加载预训练权重，创建 speaker embedding 提取接口
- [x] 4.2 实现语音段缓冲：VAD voice_start → 开始缓冲音频 → voice_end → 完整语音段送声纹提取
- [x] 4.3 实现声纹质量门控：语音段 ≥ 1.5 秒、SNR ≥ 10dB、单人说话（无重叠语音）
- [x] 4.4 实现唤醒词+声纹联合触发：唤醒词命中时从环形缓冲区取出完整语音段，同时用于唤醒词确认和声纹提取
- [x] 4.5 推送 `mic.voiceprint` 事件：包含 192-dim embedding + 置信度 + 时间戳

## 5. 身份融合引擎

- [x] 5.1 创建 `src/python/modules/fusion/` 模块：加载成员数据库，维护当前身份假设状态
- [x] 5.2 实现并行证据接收：camera.face_detected → 人脸 embedding 入队；mic.voiceprint → 声纹 embedding 入队。各自独立处理，不互相阻塞
- [x] 5.3 实现余弦相似度匹配：收到 embedding 后对数据库所有已注册成员做相似度搜索，输出 best_member_id + best_score
- [x] 5.4 实现融合决策矩阵：双高(>0.7) → 确认；人脸高+声纹低 → 暂确认；人脸低+声纹高 → 询问；双低(<0.5) → 未识别；双高不同人 → 冲突取高+询问
- [x] 5.5 实现证据累积：每次新 embedding 更新置信度状态，evidence_counter++，累积 3 次确认 → 推送 `identity.confirmed` 事件
- [x] 5.6 实现身份变更检测：对话中检测到不同人 → 推送 `identity.changing` → 暂停会话 → 重新运行融合
- [x] 5.7 融合引擎对接状态机：identity.confirmed → 触发 state.transition(Auth)；identity.unknown → 触发自动发现流程
- [x] 5.8 更新 `src/python/server/main.py`：注册 fusion 模块，扩展消息路由（identity.* 消息类型）

## 6. 角色权限系统

- [x] 6.1 创建 `src/python/modules/role/` 模块：定义 Role enum（Owner/Adult/Child/Guest）、等级优先级、权限白名单
- [x] 6.2 实现权限检查接口：can_execute(member, command) → bool，按角色+指令类型判決
- [x] 6.3 实现指令优先级抢占：Owner 可打断任何人，高等级打断低等级，同等级 FIFO
- [x] 6.4 实现角色上下文附着：identity.confirmed 事件携带 role 字段 → 状态机 state.changed 携带完整身份+角色上下文
- [x] 6.5 Child 用户实现使用时长限制：每日累计对话时间上限（默认 2 小时），超时后拒绝新指令

## 7. 成员管理系统

- [x] 7.1 创建 `src/python/modules/members/` 模块：成员注册、查询、更新、删除逻辑
- [x] 7.2 实现自动发现流水线：3 次以上(间隔≥30s)出现未知 embedding + 质量达标 → 创建"访客-NNN"记录，取均值 embedding
- [x] 7.3 实现主人手动注册流程：Step 1 姓名+角色 → Step 2 人脸采集(3-5 角度，实时反馈) → Step 3 声纹采集(3 段随机句子朗读) → Step 4 融合验证
- [x] 7.4 实现首次交互自动标识：未标识人物对话时，Frank 询问"请问怎么称呼你？" → 自动更新名称
- [x] 7.5 实现主人标识面板逻辑：列出待标识人物(序列名+出现次数+最近时间) + 已标识成员列表
- [x] 7.6 实现标识操作：主人选"访客-NNN" → 输入名字+角色 → 可选合并到已存在成员
- [x] 7.7 实现成员删除：embedding 物理删除，对话历史可选匿名化保留

## 8. UI 升级

- [x] 8.1 升级欢迎卡片：根据身份上下文显示个性化问候——"下午好，[display_name] [role_badge]" + 角色徽章（Owner 金、Adult 蓝、Child 绿、Guest 灰）
- [x] 8.2 实现成员管理面板：工具栏"👥 成员"按钮 → 展开面板 → 已标识成员列表 + 待标识列表 + 添加成员按钮
- [x] 8.3 实现注册流程 UI 向导：4 步式弹窗——①姓名+角色选择 → ②人脸采集(实时预览+进度"3/5") → ③声纹采集(显示朗读句子+录音指示) → ④验证结果
- [x] 8.4 更新标题栏：Auth/Chat 状态时标题显示"Frank - [display_name]"；未知用户显示"Frank - 访客"
- [x] 8.5 添加新消息类型 IPC 监听：identity.confirmed、identity.changing、identity.unknown、member.registered
- [x] 8.6 更新 preload.js contextBridge：暴露新事件监听接口（onIdentityConfirmed、onIdentityChanging、onMemberRegistered）

## 9. 集成验证

- [ ] 9.1 冷启动测试：首次运行 → InsightFace+SpeechBrain 模型加载 → 数据库初始化 → 进入 Idle（无已知成员）
- [ ] 9.2 主人注册测试：打开成员面板 → 添加成员 → 完成人脸+声纹采集 → 验证识别 → 数据库有记录
- [ ] 9.3 身份识别测试：已注册成员出现在摄像头前 → 人脸识别命中 → 说"Hey Frank" → 声纹命中 → 融合确认 → UI 显示姓名+角色
- [ ] 9.4 自动发现测试：新面孔出现 3 次 → 自动创建"访客-001" → 对话时询问称呼 → 标识为"王叔叔"
- [ ] 9.5 角色权限测试：Child 用户请求越权技能 → 拒绝并提示；Owner 可打断 Child 会话
- [ ] 9.6 身份变更测试：A 在对话中 → B 出现 → 检测到人脸变化 → identity.changing → 重新识别
- [ ] 9.7 模型降级测试：删除 InsightFace 模型 → 自动回退 MediaPipe 检测（无 embedding）→ 系统仍可用
