# Frank 第三轮需求 — 身份识别面板重构 + 角色体系升级 设计文档

> 日期：2026-05-31 | 分支：`develop-base-v0` | 状态：设计完成

## 需求概述

1. **身份识别界面重构**：当前面板展示静态角色卡片+权限矩阵，改为展示识别到的人物历史列表，每个条目展示身份信息、面部抓图、声纹特征、最近识别时间
2. **角色层级收纳**：将角色层级介绍和权限矩阵移到独立的"角色说明"面板
3. **标识入口**：已标识人物提供修改标识入口，未标识人物提供标识录入入口
4. **角色体系升级**：从 4 种角色（主人/成人/儿童/访客）升级为 5 种（主人/管理员/成员/访客/未登记）
5. **通知机制**：未登记人员录入后系统内通知，外部通知接口预留（邮件+IM）

---

## 一、身份识别面板重构

### 1.1 面板布局

当前 `identityPanel` 内容（身份卡片 + 角色层级卡片 + 权限矩阵）全部替换为：

```
┌─ 身份识别面板 ──────────────────────────┐
│ 标题栏：[身份识别]              [角色说明▶] │
│                                          │
│ ┌─ 统计栏 ─────────────────────────────┐ │
│ │ 已标识: N  待标识: M  历史: Total     │ │
│ └──────────────────────────────────────┘ │
│                                          │
│ ┌─ 筛选标签 ───────────────────────────┐ │
│ │ [全部] [主人] [管理员] [成员] [访客] [未标识] │
│ └──────────────────────────────────────┘ │
│                                          │
│ ┌─ 人物列表（可滚动）───────────────────┐ │
│ │ ┌─ 人物条目 (已标识) ──────────────┐ │ │
│ │ │ [面部缩略图]  [声纹频谱迷你图]   │ │ │
│ │ │ 显示名: 爸爸  角色: 👑 主人      │ │ │
│ │ │ 最近识别: 2 分钟前 · 置信度 97%  │ │ │
│ │ │ 注册时间: 2026-05-15             │ │ │
│ │ │                    [✏️ 修改标识] │ │ │
│ │ └──────────────────────────────────┘ │ │
│ │                                       │ │
│ │ ┌─ 人物条目 (未标识) ──────────────┐ │ │
│ │ │ [面部缩略图]  [声纹频谱迷你图]   │ │ │
│ │ │ 标识: 访客_A3F2  角色: ⚪ 未标识  │ │ │
│ │ │ 最近出现: 5 分钟前 · 出现 12 次  │ │ │
│ │ │ 首次发现: 2026-05-20             │ │ │
│ │ │                    [📝 标识身份] │ │ │
│ │ └──────────────────────────────────┘ │ │
│ └──────────────────────────────────────┘ │
│                                          │
│ 底部: [+ 添加成员] 按钮（打开注册向导）  │
└──────────────────────────────────────────┘
```

### 1.2 交互

| 操作 | 目标 |
|------|------|
| 点击"角色说明 ▶" | 打开 `roleInfoPanel` 滑入面板 |
| 点击"修改标识" | 弹出编辑弹窗（修改显示名/角色下拉） |
| 点击"标识身份" | 弹出标识对话框（姓名→角色→确认），或跳转注册向导 |
| 点击面部缩略图 | 放大查看（lightbox 或新窗口） |
| 筛选标签 | 按角色过滤列表，更新显示 |
| 底部"+ 添加成员" | 打开现有注册向导（wizardOverlay） |

### 1.3 数据来源

- **已标识成员**：`member.list` 返回格式扩展，每条成员增加 `face_thumbnail_path`、`voiceprint_spectrum`、`last_recognized_at`、`recognition_confidence`
- **未标识人物**：`member.pending` 返回格式扩展，每条增加 `face_thumbnail_path`、`voiceprint_spectrum`、`appearance_count`、`first_seen_at`

### 1.4 前端改动

**文件**：`src/electron/renderer/index.html`（替换 identityPanel 内容）、`src/electron/renderer/app.js`（替换渲染函数）、`src/electron/renderer/styles.css`（新增人物列表样式）

---

## 二、角色说明面板（Role Info Panel）

### 2.1 面板结构

新面板 `roleInfoPanel`，独立滑入式面板，从身份识别面板标题栏"角色说明 ▶"按钮打开。

```
┌─ 角色权限说明 ──────────────────────────┐
│                                          │
│ ┌─ 角色层级卡片 ───────────────────────┐ │
│ │ 👑 主人   等级 5  最高指令权限       │ │
│ │ 🔵 管理员 等级 4  全部指令权限       │ │
│ │ 🟢 成员   等级 3  常规指令权限       │ │
│ │ ⚪ 访客   等级 2  仅访客权限         │ │
│ │ ⬜ 未登记 等级 0  无权限（需录入）   │ │
│ └──────────────────────────────────────┘ │
│                                          │
│ ┌─ 权限矩阵表 ─────────────────────────┐ │
│ │ 权限 / 角色 │主│管│成│访│未│        │ │
│ │ 成员管理    │✓│✓│✗│✗│✗│        │ │
│ │ 系统配置    │✓│✓│✗│✗│✗│        │ │
│ │ ...         │ │ │ │ │ │            │ │
│ └──────────────────────────────────────┘ │
│                                          │
│ ┌─ 角色说明 ───────────────────────────┐ │
│ │ 主人：系统所有者，不可删除，唯一     │ │
│ │ 管理员：由主人授权，管理成员和设置   │ │
│ │ ...                                  │ │
│ └──────────────────────────────────────┘ │
└──────────────────────────────────────────┘
```

### 2.2 实现

- 纯前端展示面板，数据通过已有 `role.list` IPC 获取
- 新增面板 ID `roleInfoPanel`，接入 PanelManager 系统
- 导航栏不增加入口（通过身份面板间接打开）

---

## 三、人脸截图存储

### 3.1 流程

```
CameraPipeline._capture_loop()
    → 人脸检测到 embedding
    → IdentityFusionEngine 确认身份
    → 调用 camera_pipeline.capture_face_thumbnail(bbox)
    → 裁剪帧中人脸区域 → 128×128 缩略图 → JPEG
    → 保存到 data/faces/{member_id}_{timestamp}.jpg
    → 更新 members/unidentified 表的 face_thumbnail 字段
```

### 3.2 数据库改动

**members 表新增**：
```sql
ALTER TABLE members ADD COLUMN face_thumbnail TEXT;
```

**unidentified 表新增**：
```sql
ALTER TABLE unidentified ADD COLUMN face_thumbnail TEXT;
```

### 3.3 CameraPipeline 新增方法

```python
def capture_face_thumbnail(self, bbox: dict) -> bytes | None:
    """根据相对 bbox {x, y, width, height} 从最近帧截取人脸缩略图
    Returns: JPEG bytes (128×128) or None
    """
```

在 `_capture_loop()` 中缓存最新帧 `self._last_frame` 供截图使用。

### 3.4 IdentityFusionEngine 回调扩展

`on_identity_confirmed` 回调中增加人脸截图步骤——从 `_last_face_bbox` 获取 bbox 坐标，调用 camera pipeline 截取缩略图，保存并更新数据库。

---

## 四、声纹频谱迷你图

### 4.1 生成方式

- 后端 `AudioPipeline._try_extract_voiceprint()` 成功后：将 192 维 embedding 每 4 维取均方根 → 48-bin 频谱曲线
- 存入数据库 `voiceprint_spectrum` 字段（JSON array of 48 floats）
- 前端 48 个 CSS div 柱状条渲染为频谱迷你图

### 4.2 数据库改动

**members 表新增**：
```sql
ALTER TABLE members ADD COLUMN voiceprint_spectrum TEXT;
```

**unidentified 表新增**：
```sql
ALTER TABLE unidentified ADD COLUMN voiceprint_spectrum TEXT;
```

### 4.3 member_manager 新增方法

```python
@staticmethod
def update_voiceprint_spectrum(person_id: str, spectrum_bins: list[float], is_member: bool = True):
    """更新声纹频谱数据到 members 或 unidentified 表"""

@staticmethod
def get_voiceprint_spectrum(person_id: str) -> list[float] | None:
    """获取声纹频谱数据"""
```

### 4.4 前端展示

- 48 个 `.spec-mini-bar` 柱状条，使用与预览窗口一致的暖色→冷色渐变
- 有频谱数据：显示柱状图 + 标签"声纹已采集 · N 段"
- 无频谱数据：灰色占位符 + 标签"声纹待采集"

---

## 五、角色体系变更

### 5.1 角色对照

| 旧角色 | 新角色 | 等级 | 说明 |
|--------|--------|------|------|
| `owner` | `owner` (主人) | 5 | 不变，最高权限 |
| `adult` | `admin` (管理员) | 4 | 原"成人"，全部指令权限 |
| `child` | `member` (成员) | 3 | 原"儿童"，除管理外的指令权限 |
| `guest` | `guest` (访客) | 2 | 不变，仅访客权限 |
| — | `unregistered` (未登记) | 0 | **新增**，无权限，引导录入 |

### 5.2 注册向导角色选项

保持 4 种可选角色：主人 / 管理员 / 成员 / 访客（"未登记"不出现，由系统自动判定）

### 5.3 后端改动

**role_manager.py**：更新默认角色定义，将 `adult`/`child` 替换为 `admin`/`member`，新增 `unregistered`

**member_manager.py**：`set_registration_info()` 角色校验更新为新的 4 种（owner/admin/member/guest）

**数据库**：roles 表需迁移（若已有数据，执行 UPDATE 转换 adult→admin, child→member，新增 unregistered 行）

### 5.4 前端改动

- 注册向导角色卡片标签：成人→管理员、儿童→成员
- 角色颜色/图标映射更新：
  - owner: 👑 金色
  - admin: 🔵 蓝色
  - member: 🟢 绿色
  - guest: ⚪ 灰色
  - unregistered: ⬜ 暗灰色

---

## 六、通知接口预留

### 6.1 系统内通知（本轮实现）

- 未登记人物提交录入后 → `member.identified` 事件（已有）
- 前端通知面板显示："新访客已录入：{display_name}，角色：访客"

### 6.2 外部通知接口（新建 stub 模块）

**文件**：`src/python/modules/notification/__init__.py` + `notifier.py`

```python
class ExternalNotifier:
    """外部通知服务接口"""

    async def send_email(self, to: str, subject: str, body: str):
        """SMTP 邮件发送 (stub)"""
        raise NotImplementedError("SMTP not configured")

    async def send_im(self, service: str, webhook_url: str, message: str):
        """IM Webhook 发送 (stub)"""
        raise NotImplementedError("IM webhook not configured")

    async def notify_owners(self, event: str, details: dict):
        """通知所有主人/管理员
        1. 获取 owner + admin 成员列表
        2. 如果邮件/IM 已启用 → 发送通知
        3. 否则 → 记录日志 + 系统内通知
        """
```

### 6.3 配置预留

在 `frank.yaml` 中新增配置段：

```yaml
notification:
  email:
    enabled: false
    smtp_host: ""
    smtp_port: 587
    sender: ""
    username: ""
    password: ""
  im:
    enabled: false
    webhook_url: ""
    service: ""  # wecom | dingtalk | slack
```

---

## 七、数据库迁移

```sql
-- 角色迁移
UPDATE roles SET name = 'admin', display_name = '管理员' WHERE name = 'adult';
UPDATE roles SET name = 'member', display_name = '成员' WHERE name = 'child';
INSERT OR IGNORE INTO roles (name, display_name, level, description) 
  VALUES ('unregistered', '未登记', 0, '系统自动发现的未标识人物，无任何权限');

-- 已标识成员扩展字段
ALTER TABLE members ADD COLUMN face_thumbnail TEXT;
ALTER TABLE members ADD COLUMN voiceprint_spectrum TEXT;

-- 未标识人物扩展字段
ALTER TABLE unidentified ADD COLUMN face_thumbnail TEXT;
ALTER TABLE unidentified ADD COLUMN voiceprint_spectrum TEXT;
```

---

## 八、文件改动清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/electron/renderer/index.html` | 修改 | 替换 identityPanel 内容，新增 roleInfoPanel |
| `src/electron/renderer/styles.css` | 修改 | 新增人物列表样式、频谱迷你图样式、筛选标签样式 |
| `src/electron/renderer/app.js` | 修改 | 新增人物列表渲染函数、筛选逻辑、弹窗交互 |
| `src/python/modules/camera/camera_pipeline.py` | 修改 | 缓存最新帧 + `capture_face_thumbnail()` 方法 |
| `src/python/modules/audio/audio_pipeline.py` | 修改 | 声纹提取后生成 48-bin 频谱 + 存入数据库 |
| `src/python/modules/fusion/identity_fusion.py` | 修改 | 身份确认时触发人脸截图保存 |
| `src/python/modules/members/member_manager.py` | 修改 | 新角色校验 + `update_voiceprint_spectrum()` + `get_voiceprint_spectrum()` |
| `src/python/modules/role/role_manager.py` | 修改 | 角色定义从 4 种更新为 5 种 |
| `src/python/shared/database.py` | 修改 | 数据库迁移 SQL |
| `src/python/server/main.py` | 修改 | role.list 返回新角色结构 |
| `src/python/modules/notification/__init__.py` | **新建** | 通知模块初始化 |
| `src/python/modules/notification/notifier.py` | **新建** | ExternalNotifier stub |
| `data/faces/` | **新建** | 人脸截图存储目录 |

---

## 九、设计决策记录

| 决策 | 选项 | 理由 |
|------|------|------|
| 面部抓图展示 | 后端存储实际截图 | 用户明确要求展示面部图像 |
| 声纹特征展示 | 48-bin 频谱迷你图 | 通过降维可视化直观展示声纹特征 |
| 通知机制 | 系统内通知 + 外部接口预留 | 本轮聚焦系统内可用，外部集成后续对接 |
| 角色说明 | 独立滑入面板 | 保持面板系统一致性，不污染身份面板内容 |
| 注册向导角色 | 保持 4 种 | 简化录入流程，"未登记"由系统自动判定 |
| 角色迁移 | 数据库 UPDATE + ALTER | 保留现有成员数据，最小化数据丢失风险 |

---

## 十、未涵盖 / 待定

- **IM/邮件实际对接**：外部通知服务 stub 已创建，配置段已预留，实际 SMTP/Webhook 对接留待后续迭代
- **人脸缩略图放大查看**：本期点击缩略图仅放大预览，后续可支持多角度截图轮播
- **声纹频谱交互**：本期为静态展示，后续可支持点击展开查看详细声纹匹配历史
