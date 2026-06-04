# Frank 人脸识别稳定性优化 — 设计方案

**日期**: 2026-06-05
**状态**: 已确认
**版本**: v1.0

---

## 一、问题定义

当前系统在以下场景中，会将同一采集人物错误记录为多个不同身份：

| 场景 | 根本原因 |
|------|---------|
| 头部角度变化（侧脸/低头/仰头） | 每人仅存 1 个平均 embedding，无法覆盖多角度外观 |
| 表情变换（笑/说话/无表情） | embedding 对表情敏感，表情偏移被误判为新身份 |
| 部分面部遮盖（手/口罩/眼镜） | 遮挡帧 embedding 质量低，与注册 embedding 距离过大 |
| 多人画面中人物交叉/遮挡 | 无跟踪机制，人脸丢失后重建即视为新人 |
| 人物短暂离开后重入画面 | 无 Re-ID 机制，重入后被分配新的 track/身份 |

**设计目标**：同一采集人物的识别稳定性从当前预估 50-60% 提升到 90%+ 的正确持续识别率。

---

## 二、总体架构

```
摄像头帧
    │
    ├─→ [人脸检测 + Embedding提取] ──→ [质量门控] ──→ [人脸代价矩阵]
    │                                                        │
    ├─→ [人物检测] ──→ [外观特征提取(ReID)] ──→ [外观代价矩阵]
    │                                                        │
    ├─→ [Kalman滤波器预测] ──→ [运动代价矩阵] ──────────────┤
    │                                                        │
    └──────────────────→ [三维联合代价矩阵] ←────────────────┘
                                    │
                         [匈牙利算法最优分配]
                                    │
                         [级联匹配 Cascade Matching]
                                    │
                    ┌───────────────┴───────────────┐
                    │   Track 生命周期管理           │
                    │   CANDIDATE→ACTIVE→LOST→REMOVED│
                    └───────────────┬───────────────┘
                                    │
                         [身份槽位 Identity Slot]
                                    │
                    ┌───────────────┴───────────────┐
                    │   时序平滑投票 (滑动窗口)       │
                    └───────────────┬───────────────┘
                                    │
                         [多样本图库匹配 + 更新]
                                    │
                              身份输出
```

**核心原则**：跟踪管线负责身份的**时空连续性**（"这是同一个人"），识别管线负责身份的**精确归属**（"这个人是张三"）。两条管线并行运转，互相补充。

---

## 三、模块设计

### 模块 1：多人时空跟踪器（Person Tracker）

**技术选型**：DeepSORT 范式（运动 + 外观 + 人脸三维匹配），替代当前无跟踪状态的逐帧独立匹配。

#### 核心组件

| 组件 | 功能 |
|------|------|
| Kalman 滤波器 | 8 维状态向量 `(x, y, w, h, dx, dy, dw, dh)`，匀速模型预测下一帧位置 |
| 外观特征提取 | 轻量 CNN（OSNet 或 MobileNet-ReID）提取 128 维外观向量，对衣着/体型编码 |
| 三维代价矩阵 | `Cost = α × 运动(马氏距离) + β × 外观(余弦距离) + γ × 人脸(余弦距离)`，权重可动态调整 |
| 匈牙利算法 | 全局最优匹配，避免贪心导致的局部最优分配 |
| 级联匹配 | 优先匹配丢失时间短的 track（更可靠），丢失长的 track 只能用低分检测匹配 |

#### Track 生命周期

```
CANDIDATE → (连续3帧确认) → ACTIVE → (1帧未匹配) → LOST → (超时60帧) → REMOVED
                 ↑                          │
                 └──── (重新匹配) ←─────────┘
```

| 状态 | 说明 |
|------|------|
| CANDIDATE | 新检测，需连续 3 帧确认才升级为 ACTIVE，过滤误检 |
| ACTIVE | 活跃跟踪，每帧更新 Kalman 状态和外观特征（指数移动平均 0.9） |
| LOST | 短暂丢失（遮挡/出框），Kalman 预测维持位置，保留外观特征 |
| REMOVED | LOST 超过 60 帧（约 2 秒），释放资源 |

#### 多人交叉防护

- 交叉时外观权重 β 临时从 0.3 提升至 0.6
- Kalman 协方差矩阵适度膨胀，增大位置容差
- 交叉结束后验证前后外观一致性，检测到 ID 交换时回滚修正

#### 关键参数

| 参数 | 建议值 | 说明 |
|------|--------|------|
| α（运动权重） | 0.4 | 正常场景下的运动代价权重 |
| β（外观权重） | 0.3（常态）/ 0.6（交叉时） | 交叉时提升外观区分度 |
| γ（人脸权重） | 0.3 | 有人脸时参与匹配 |
| CANDIDATE 确认帧 | 3 | 过滤误检 |
| LOST 超时 | 60 帧（~2 秒） | 短暂遮挡/转身容忍 |
| 外观特征指数衰减 | 0.9 | 逐步更新外观，适应光照变化 |

---

### 模块 2：多样本图库匹配

**现状**：注册时采集 N 张人脸 → 取平均 → 存 1 个 embedding  
**改为**：注册时采集 N 张人脸 → K-Means 聚类 → 存 K 个代表性 embedding（K=3~5）

#### 匹配方式改变

- **旧**：`max(cosine(query, avg_embedding_m))` 对所有 member m
- **新**：`max(cosine(query, gallery_embedding_m_k))` 对所有 member m 的所有图库样本 k

即用 max-pooling 替代单一匹配，每个 query 取图库中最佳匹配。

#### 图库维护

- 成功确认身份时，若新 embedding 与图库中所有已有样本距离 > 0.2，则追加到图库（增量扩展外观覆盖）
- 图库超过上限（10 个样本）时，移除与均值最远的样本（离群点淘汰）
- 定期（每天）对图库做质量审计，移除检测置信度 < 0.6 的低质量样本

---

### 模块 3：质量门控

在 embedding 进入匹配前，先进行质量评估。任一指标不通过，该帧的人脸 embedding 不参与匹配（但仍可用于跟踪器的运动/外观匹配）。

| 质量指标 | 计算方式 | 丢弃阈值 |
|----------|---------|---------|
| 检测置信度 | InsightFace `det_score` | < 0.5 |
| 人脸大小 | bbox 面积 / 帧面积 | < 5% |
| 人脸角度 | landmarks 估算 pitch / yaw / roll | yaw > 45° 或 pitch > 30° |
| 模糊度 | Laplacian 方差 | < 100 |
| 遮挡比例 | landmarks 可见点数 / 68（总 landmarks） | < 70%（即遮挡 > 30%） |

---

### 模块 4：身份槽位（Identity Slot）+ 时序平滑

每个活跃 track 维护一个身份槽位：

```
IdentitySlot {
    track_id: int
    bound_member_id: str | None      # 当前绑定的成员 ID
    hypothesis_history: deque[10]    # 最近 10 次识别结果 (member_id, score)
    face_quality_count: int          # 通过质量门控的人脸帧数
    last_good_face_time: float       # 最后通过门控的时间戳
    last_match_score: float          # 最近匹配分数
}
```

#### 身份绑定规则

| 规则 | 条件 | 动作 |
|------|------|------|
| 绑定 | 连续 `N=5` 帧匹配到同一 member 且平均分 > 0.55 | 槽位绑定该 member |
| 保持绑定 | `当前时间 - last_good_face_time < 3 秒` | 即使当前无匹配，继续输出绑定的身份 |
| 解绑 | `当前时间 - last_good_face_time > 3 秒` | 身份退化为 UNKNOWN |
| 切换 | 连续 `N=5` 帧匹配到不同 member | 执行身份切换，发送 identity.changing 事件 |

#### 效果

- 短暂转身（< 3 秒）不会丢失身份
- 单帧误匹配不会触发身份跳变
- 身份切换有充分证据后才执行

---

### 模块 5：重识别（Re-ID）

**目标**：人物短暂离开画面后重新进入时，恢复其之前的身份绑定。

**策略**：
- 记录每个 LOST → REMOVED 的 track 的最后外观特征向量和最后位置
- 新 track 创建时，与最近 30 秒内移除的 track 做外观特征余弦相似度比对
- 若外观相似度 > 0.7 且位置合理（在出框位置附近出现），则恢复原 track 的身份绑定和 member_id

---

## 四、数据库变更

### members 表新增列

```sql
ALTER TABLE members ADD COLUMN face_gallery TEXT;
-- JSON 数组，存储 K 个 face_embedding (base64 编码)
-- 格式: ["<base64_emb1>", "<base64_emb2>", ...]
-- 每个 embedding 为 512 维 float32
```

### 新增 person_tracks 表（可选，用于离线分析和调试）

```sql
CREATE TABLE person_tracks (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    track_start REAL NOT NULL,
    track_end REAL,
    bound_member_id TEXT,
    max_appearance_count INTEGER DEFAULT 0,
    avg_face_score REAL DEFAULT 0.0
);
```

---

## 五、性能考量

| 模块 | 计算开销 | 优化措施 |
|------|---------|---------|
| 人物检测 | 中 | 复用 InsightFace 或加轻量 YOLO-tiny |
| ReID 特征提取 | 中 | OSNet 轻量版，2-3ms/人 |
| Kalman + 匈牙利 + 级联匹配 | 低 | < 1ms（O(n³)，n < 10 时忽略不计） |
| 多样本匹配 | 低（略增） | 每人 3-5 个 embedding，暴力搜索仍在微秒级 |
| 质量评估 | 低 | 大部分指标复用 InsightFace 已有输出 |

**预估总增加延迟**：< 10ms/帧，不影响实时性。

---

## 六、实施计划

| Phase | 内容 | 预估工作量 | 优先级 |
|-------|------|-----------|--------|
| **P1** | 多人 DeepSORT 跟踪器（Kalman + 外观特征 + 三维代价矩阵 + 匈牙利 + 级联匹配 + Track 生命周期） | 3-5 天 | P0 |
| **P2** | 多样本图库（K-Means 聚类注册 + max-pooling 匹配 + 增量更新 + 质量审计） | 2-3 天 | P0 |
| **P3** | 质量门控 + 身份槽位 + 时序平滑投票 | 2-3 天 | P0 |
| **P4** | ReID 恢复 + 多人交叉回滚 + 参数联调优化 | 2-3 天 | P1 |

---

## 七、影响范围

### 需修改的文件

| 文件 | 变更 |
|------|------|
| `src/python/modules/camera/camera_pipeline.py` | 新增质量评估输出（角度/模糊度/遮挡）；新增外观特征提取调用 |
| `src/python/modules/fusion/identity_fusion.py` | 重构为：接收 track 绑定的身份假设 + 时序平滑；集成多样本匹配 |
| `src/python/shared/database.py` | 新增 `face_gallery` 列；`search_by_face_embedding` 改为 max-pooling 图库匹配；新增 `update_face_gallery` / `audit_face_gallery` |
| `src/python/modules/members/member_manager.py` | 注册流程改为 K-Means 聚类存储多个代表性 embedding |
| `src/python/server/main.py` | 新增 PersonTracker 初始化与事件绑定 |
| **新增** `src/python/modules/tracking/person_tracker.py` | DeepSORT 多人跟踪器 + 身份槽位管理 |
| **新增** `src/python/modules/tracking/reid_extractor.py` | 外观特征提取（OSNet 或 MobileNet-ReID） |

### 不受影响

- 前端（Electron 渲染进程）— 身份事件协议保持不变
- 声纹管线 — 独立运作，不受影响
- WebSocket 事件协议 — `identity.confirmed` / `identity.changing` / `identity.unknown` 结构不变
