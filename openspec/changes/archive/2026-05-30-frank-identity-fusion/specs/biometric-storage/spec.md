# 生物特征存储能力 - 规格说明

## 概述

为 Frank（弗兰克）Phase 2 新增"生物特征存储"（biometric-storage）能力，提供基于 SQLite 的人脸与语音嵌入向量的持久化存储、检索与更新功能。该能力是身份融合系统的底层数据基础设施，确保所有生物特征数据在设备本地安全存储，绝不传输至网络。

---

## ADDED Requirements

### Requirement: SQLite 数据库与表结构

#### Scenario: 数据库初始化

系统启动时，在 `data/frank.db` 路径创建 SQLite 数据库文件。若文件不存在则自动创建；若已存在则打开连接。数据库包含以下核心表：

**members 表（已识别的成员）**

| 列名 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 成员唯一标识 |
| display_name | TEXT | NOT NULL | 显示名称 |
| role | TEXT | DEFAULT '' | 角色描述 |
| face_embedding | BLOB | NULL | 人脸嵌入向量，512 个 float32 值序列化后的字节流 |
| typical_distance_cm | REAL | NULL | 典型识别距离（厘米） |
| voice_embedding | BLOB | NULL | 语音嵌入向量，192 个 float32 值序列化后的字节流 |
| labeled | INTEGER | NOT NULL DEFAULT 0 | 是否已人工标注（0=未标注，1=已标注） |
| created_at | TEXT | NOT NULL DEFAULT (datetime('now')) | 创建时间（ISO 8601） |
| last_active_at | TEXT | NOT NULL DEFAULT (datetime('now')) | 最后活跃时间 |
| appearance_count | INTEGER | NOT NULL DEFAULT 0 | 出现次数累计 |

**unidentified 表（未识别的陌生人）**

与 members 表具有相同的列定义，但 `labeled` 列固定为 0。此表用于临时存储未能匹配到已知成员的生物特征数据，便于后续人工标注或聚类分析。

**skill_preferences 表（技能偏好）**

| 列名 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 自增主键 |
| member_id | INTEGER | NOT NULL REFERENCES members(id) ON DELETE CASCADE | 关联的成员 ID |
| skill_name | TEXT | NOT NULL | 技能名称 |
| preferences_json | TEXT | NOT NULL DEFAULT '{}' | 偏好配置，JSON 格式 |

`skill_preferences` 表建立 `(member_id, skill_name)` 联合唯一索引，确保每个成员对每个技能只有一条偏好记录。

**version 表（数据库迁移版本管理）**

| 列名 | 类型 | 约束 | 说明 |
|---|---|---|---|
| version | INTEGER | NOT NULL | 当前数据库 schema 版本号 |
| applied_at | TEXT | NOT NULL DEFAULT (datetime('now')) | 迁移应用时间 |

---

### Requirement: 嵌入向量序列化

#### Scenario: 序列化与反序列化

**序列化流程（存储方向）：**

1. 输入：numpy float32 类型数组，形状为 `(512,)`（人脸）或 `(192,)`（语音）。
2. 对嵌入向量执行 L2 归一化：`vector = vector / np.linalg.norm(vector)`。
3. 调用 `numpy.ndarray.tobytes()` 将归一化后的数组转换为字节流。
4. 将字节流写入 BLOB 列。

**反序列化流程（读取方向）：**

1. 从 BLOB 列读取字节流。
2. 调用 `numpy.frombuffer(blob_bytes, dtype=np.float32)` 恢复为 numpy 数组。
3. 根据嵌入类型将数组 reshape 为 `(512,)` 或 `(192,)`。
4. 对恢复后的向量执行 L2 归一化，确保读取值与存储值一致。

**归一化要求：**

所有嵌入向量在序列化前和反序列化后均需执行 L2 归一化。归一化公式为：

```
v_normalized = v / max(||v||_2, 1e-12)
```

其中分母加入极小值 `1e-12` 以防止零向量除零错误。

---

### Requirement: CRUD 操作

#### Scenario: 增加成员（add_member）

**输入参数：**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| display_name | str | 是 | 显示名称 |
| role | str | 否 | 角色，默认为空字符串 |
| face_embedding | numpy.ndarray | 否 | 形状为 (512,) 的 float32 数组 |
| voice_embedding | numpy.ndarray | 否 | 形状为 (192,) 的 float32 数组 |
| typical_distance_cm | float | 否 | 典型识别距离（厘米） |

**行为：**

1. 若提供了 `face_embedding`，执行 L2 归一化并序列化为 BLOB。
2. 若提供了 `voice_embedding`，执行 L2 归一化并序列化为 BLOB。
3. 向 `members` 表插入一条新记录。
4. 返回新记录的 `id`。

**异常：**

- 若 `display_name` 为空或仅含空白字符，抛出 `ValueError`。

#### Scenario: 获取成员（get_member）

**输入参数：**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| member_id | int | 是 | 成员 ID |

**行为：**

1. 根据 `member_id` 从 `members` 表查询。
2. 若存在，反序列化 `face_embedding` 和 `voice_embedding` BLOB 为 numpy 数组。
3. 以字典形式返回成员信息（包含反序列化后的 numpy 数组）。
4. 若不存在，返回 `None`。

#### Scenario: 更新成员（update_member）

**输入参数：**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| member_id | int | 是 | 成员 ID |
| display_name | str | 否 | 新的显示名称 |
| role | str | 否 | 新的角色 |
| typical_distance_cm | float | 否 | 新的典型识别距离 |
| face_embedding | numpy.ndarray | 否 | 新的完整人脸嵌入向量 |
| voice_embedding | numpy.ndarray | 否 | 新的完整语音嵌入向量 |

**行为：**

1. 根据 `member_id` 查找成员。若不存在，抛出 `ValueError`。
2. 仅更新显式提供的字段（`**kwargs` 模式，不修改未提供的字段）。
3. 若提供了 `face_embedding`，执行 L2 归一化并序列化，覆盖原有值。
4. 若提供了 `voice_embedding`，执行 L2 归一化并序列化，覆盖原有值。
5. 自动更新 `last_active_at` 为当前时间。
6. 返回更新后的成员信息。

#### Scenario: 删除成员（delete_member）

**输入参数：**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| member_id | int | 是 | 成员 ID |

**行为：**

1. 根据 `member_id` 删除 `members` 表中的记录。
2. 级联删除 `skill_preferences` 表中该成员的所有偏好记录。
3. 若记录不存在，静默成功（不抛出异常）。
4. 返回 `True` 表示执行成功。

#### Scenario: 列出所有成员（list_all_members）

**输入参数：**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| include_unidentified | bool | 否 | 是否包含未识别记录，默认 False |

**行为：**

1. 查询 `members` 表中的所有记录（当 `include_unidentified=False` 时）。
2. 若 `include_unidentified=True`，额外查询 `unidentified` 表中的记录。
3. 对每条记录中的 BLOB 字段执行反序列化。
4. 返回成员字典的列表。

#### Scenario: 列出未识别记录（list_unidentified）

**行为：**

1. 查询 `unidentified` 表中的所有记录。
2. 对每条记录中的 BLOB 字段执行反序列化。
3. 返回未识别记录字典的列表。

---

### Requirement: 余弦相似度搜索

#### Scenario: 通过人脸嵌入向量搜索（get_by_face_embedding）

**输入参数：**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| query_embedding | numpy.ndarray | 是 | 形状为 (512,) 的查询嵌入向量 |
| top_n | int | 否 | 返回前 N 个结果，默认为 5 |
| threshold | float | 否 | 匹配阈值，默认为 0.5 |

**行为：**

1. 对 `query_embedding` 执行 L2 归一化。
2. 查询 `members` 表中所有 `face_embedding` 非空的记录。
3. 对每条记录，将存储的 BLOB 反序列化为 numpy 数组。
4. 计算余弦相似度：

   ```
   similarity = np.dot(query_embedding, stored_embedding)
   ```

   由于所有向量已 L2 归一化，点积等价于余弦相似度。

5. 过滤掉相似度低于 `threshold` 的结果。
6. 按相似度降序排列，取前 `top_n` 个结果。
7. 返回列表，每个元素为 `(member_id, display_name, similarity_score)` 元组。

**当 threshold=0 时：** 返回所有结果，不进行过滤（仅按相似度降序返回前 top_n 个）。

#### Scenario: 通过语音嵌入向量搜索（get_by_voice_embedding）

**输入参数与行为**与 `get_by_face_embedding` 一致，但操作 `voice_embedding` 列，查询嵌入形状为 `(192,)`。

#### Scenario: 匹配判断

余弦相似度 >= 0.5 视为"匹配成功"（match found）。低于该阈值视为"无匹配"。该阈值可通过配置调整。

---

### Requirement: 安全保障

#### Scenario: 数据库文件权限

1. 数据库文件 `data/frank.db` 创建后，立即将文件权限设置为仅限当前操作系统用户可读写。
2. 在 Windows 系统上，禁用"继承权限"，仅保留当前用户的完全控制权限。
3. 在 Linux/macOS 系统上，设置文件权限为 `0600`（所有者读写，其他用户无权限）。
4. 数据库文件所在目录 `data/` 的权限设置为 `0700`（所有者完全控制，其他用户无权限）。
5. 上述权限设置在数据库首次创建时执行，并在每次启动时验证；若权限不匹配则重置为安全值。

#### Scenario: 嵌入向量不可逆性

1. 存储的嵌入向量是经过 L2 归一化的特征向量，属于不可逆的数学表示。
2. 从嵌入向量无法重构原始人脸图像或语音音频。
3. 系统中不存储任何原始图像或原始音频数据。
4. 仅存储经过特征提取模型处理后的嵌入向量（feature vectors）。

#### Scenario: 数据隔离

1. 所有生物特征数据严格存储在本地设备上。
2. 数据库文件永不通过任何网络接口传输。
3. 系统不提供任何数据导出/上传至网络的功能。
4. 所有 CRUD 操作仅在本地进程内完成，不涉及任何远程过程调用（RPC）。

---

### Requirement: 自适应更新（Adaptive Update）

#### Scenario: 嵌入向量加权平均更新（update_embeddings）

**输入参数：**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| member_id | int | 是 | 成员 ID |
| new_face_embedding | numpy.ndarray | 否 | 新的人脸嵌入向量 |
| new_voice_embedding | numpy.ndarray | 否 | 新的语音嵌入向量 |
| old_weight | float | 否 | 旧向量的权重，默认 0.7 |
| new_weight | float | 否 | 新向量的权重，默认 0.3 |

**行为：**

1. 根据 `member_id` 从 `members` 表获取现有记录。
2. 若成员不存在，抛出 `ValueError`。
3. 若提供了 `new_face_embedding`：
   a. 对 `new_face_embedding` 执行 L2 归一化。
   b. 从数据库读取现有的 `face_embedding` BLOB，反序列化为 numpy 数组。
   c. 若数据库中有现有向量，计算加权平均：

      ```
      updated_face = old_weight * existing_face + new_weight * new_face
      ```

   d. 若数据库中现有向量为空（NULL），直接使用 `new_face_embedding`。
   e. 对加权平均后的向量执行 L2 归一化。
   f. 序列化并写回数据库。
4. 若提供了 `new_voice_embedding`：执行类似流程，嵌入维数为 192。
5. `old_weight` 和 `new_weight` 必须满足 `old_weight + new_weight == 1.0`（允许 1e-6 浮点误差），否则抛出 `ValueError`。
6. 自动更新 `last_active_at` 为当前时间。
7. 若同时提供了人脸和语音嵌入，两者独立进行加权平均。

**权重配置说明：**

默认权重比 `0.7 旧 + 0.3 新` 倾向于保持历史特征的稳定性，防止单次错误识别导致特征漂移。在系统冷启动阶段（样本量较少时），可临时调高 `new_weight` 以加速收敛。权重比可通过配置对象全局设置。

---

### Requirement: 数据库迁移支持

#### Scenario: Schema 版本检查

1. 数据库连接建立后，检查 `version` 表是否存在。
2. 若 `version` 表不存在，视为初始状态（版本 0），自动执行所有迁移脚本以建立最新 schema。
3. 若 `version` 表存在，读取当前版本号。
4. 比较当前版本号与代码中定义的目标版本号：
   - 若当前版本 < 目标版本：按版本号升序依次执行迁移脚本。
   - 若当前版本 == 目标版本：跳过迁移，正常启动。
   - 若当前版本 > 目标版本：抛出异常，提示数据库版本来自更新的软件版本，拒绝启动。

#### Scenario: 迁移脚本执行

1. 每个迁移脚本以版本号命名，格式为 `migration_<version>.sql`，存放在 `data/migrations/` 目录下。
2. 迁移脚本包含完整的 SQL 语句（DDL 和/或 DML），在单个事务中执行。
3. 迁移执行成功后，向 `version` 表插入一条新记录，记录版本号和迁移应用时间。
4. 任一迁移脚本执行失败，事务回滚，抛出异常并记录错误日志。
5. 迁移脚本示例：

   `migration_001.sql`：

   ```sql
   CREATE TABLE IF NOT EXISTS members (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       display_name TEXT NOT NULL,
       role TEXT DEFAULT '',
       face_embedding BLOB,
       typical_distance_cm REAL,
       voice_embedding BLOB,
       labeled INTEGER NOT NULL DEFAULT 0,
       created_at TEXT NOT NULL DEFAULT (datetime('now')),
       last_active_at TEXT NOT NULL DEFAULT (datetime('now')),
       appearance_count INTEGER NOT NULL DEFAULT 0
   );
   CREATE TABLE IF NOT EXISTS unidentified (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       display_name TEXT NOT NULL DEFAULT '',
       role TEXT DEFAULT '',
       face_embedding BLOB,
       typical_distance_cm REAL,
       voice_embedding BLOB,
       labeled INTEGER NOT NULL DEFAULT 0,
       created_at TEXT NOT NULL DEFAULT (datetime('now')),
       last_active_at TEXT NOT NULL DEFAULT (datetime('now')),
       appearance_count INTEGER NOT NULL DEFAULT 0
   );
   CREATE TABLE IF NOT EXISTS skill_preferences (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       member_id INTEGER NOT NULL REFERENCES members(id) ON DELETE CASCADE,
       skill_name TEXT NOT NULL,
       preferences_json TEXT NOT NULL DEFAULT '{}'
   );
   CREATE UNIQUE INDEX IF NOT EXISTS idx_skill_preferences_member_skill
       ON skill_preferences(member_id, skill_name);
   CREATE TABLE IF NOT EXISTS version (
       version INTEGER NOT NULL,
       applied_at TEXT NOT NULL DEFAULT (datetime('now'))
   );
   INSERT INTO version (version) VALUES (1);
   ```

#### Scenario: 向后兼容

1. 迁移脚本设计需保证向前兼容——新版本代码应能读取旧版本数据库。
2. 禁止破坏性变更（如删除列、重命名表），除非提供数据迁移脚本。
3. 所有 schema 变更必须通过迁移脚本完成，禁止直接手动修改数据库文件。

---

## 附录

### 数据库连接管理

- 使用连接池或单例模式管理数据库连接，避免重复创建。
- 写操作使用事务包装，确保原子性。
- 每次写操作后自动提交（auto-commit），或使用上下文管理器显式控制事务边界。

### 错误处理规范

所有公共方法在遇到以下情况时应抛出明确的异常：

| 异常 | 触发条件 |
|---|---|
| `ValueError` | 参数校验失败（如空名称、权重和不等于 1） |
| `RuntimeError` | 数据库操作失败（如连接断开、磁盘满） |
| `FileNotFoundError` | 数据库文件被外部删除 |
| `PermissionError` | 数据库文件权限不足 |

### 性能考量

- 对于 `get_by_face_embedding` 和 `get_by_voice_embedding` 这类全表扫描的相似度搜索，在成员数量超过 1000 时建议引入近似最近邻（ANN）索引，如 SQLite 的 FTS5 虚拟表配合向量索引扩展（如 sqlite-vss），或在外层引入 FAISS 索引缓存。
- 嵌入向量列建议在未来的迁移中添加 CHECK 约束，验证 BLOB 长度是否符合预期（人脸 2048 字节 = 512 × 4，语音 768 字节 = 192 × 4）。
