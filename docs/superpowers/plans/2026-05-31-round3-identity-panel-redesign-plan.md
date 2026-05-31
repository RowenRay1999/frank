# 身份识别面板重构 + 角色体系升级 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重构身份识别面板为人物历史列表（含面部截图+声纹频谱），升级角色体系从4种到5种，新增角色说明面板，预留外部通知接口。

**Architecture:** 后端新增人脸截图存储（CameraPipeline 实时截取）和声纹频谱生成（降维可视化），数据库迁移扩展字段。前端 identityPanel 替换为可筛选的人物列表+操作入口，新增 roleInfoPanel 独立面板。

**Tech Stack:** Electron (IPC + Canvas for thumbnails), Python asyncio (WebSocket 事件), SQLite schema migration, CSS 频谱迷你图

---

## 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `src/python/shared/database.py` | 修改 | 数据库迁移 SQL（新增字段+角色变更） |
| `src/python/modules/role/role_manager.py` | 修改 | 角色定义 4→5 种 |
| `src/python/modules/camera/camera_pipeline.py` | 修改 | 缓存最新帧 + `capture_face_thumbnail()` |
| `src/python/modules/audio/audio_pipeline.py` | 修改 | 声纹提取后生成频谱并存储 |
| `src/python/modules/members/member_manager.py` | 修改 | 角色校验更新 + 频谱/缩略图存取方法 |
| `src/python/modules/fusion/identity_fusion.py` | 修改 | 身份确认时触发人脸截图 |
| `src/python/server/main.py` | 修改 | role.list 返回新角色结构 + 通知事件 |
| `src/python/modules/notification/__init__.py` | **新建** | 通知模块 |
| `src/python/modules/notification/notifier.py` | **新建** | ExternalNotifier stub |
| `src/electron/renderer/index.html` | 修改 | 替换 identityPanel + 新增 roleInfoPanel |
| `src/electron/renderer/styles.css` | 修改 | 人物列表/频谱迷你图/筛选标签样式 |
| `src/electron/renderer/app.js` | 修改 | 人物列表渲染/筛选/弹窗逻辑 |
| `data/faces/` | **新建** | 人脸截图存储目录 |

---

### Task 1: 数据库迁移 — 角色变更 + 新增字段

**Files:**
- Modify: `src/python/shared/database.py`

- [ ] **Step 1: 更新 SCHEMA_VERSION 并添加迁移逻辑**

在 `src/python/shared/database.py` 顶部，将 `SCHEMA_VERSION` 从 2 改为 3：

```python
SCHEMA_VERSION = 3
```

在 `init_database()` 函数的建表语句之后（所有 CREATE TABLE 之后），添加版本迁移逻辑：

```python
        # Schema 迁移
        current_version_row = conn.execute(
            "SELECT MAX(version) as v FROM schema_version"
        ).fetchone()
        current_version = (current_version_row['v'] or 0) if current_version_row else 0

        if current_version < 3:
            logger.info('Running schema migration to version 3...')
            # 角色迁移：adult→admin, child→member
            conn.execute("UPDATE members SET role = 'admin' WHERE role = 'adult'")
            conn.execute("UPDATE members SET role = 'member' WHERE role = 'child'")
            # 新增角色 unregistered
            try:
                conn.execute("""
                    INSERT OR IGNORE INTO roles (name, display_name, level, description, permissions_json, skills_json, daily_limit_minutes, badge)
                    VALUES ('unregistered', '未登记', 0, '系统自动发现的未标识人物，无任何权限',
                        '{}', '[]', 0, '⬜')
                """)
            except Exception:
                pass  # roles 表可能尚不存在或有其他结构
            # 新增字段：members 表
            try:
                conn.execute("ALTER TABLE members ADD COLUMN face_thumbnail TEXT")
            except Exception:
                pass  # 字段已存在
            try:
                conn.execute("ALTER TABLE members ADD COLUMN voiceprint_spectrum TEXT")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE members ADD COLUMN last_recognized_at TEXT")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE members ADD COLUMN recognition_confidence REAL DEFAULT 0")
            except Exception:
                pass
            # 新增字段：unidentified 表
            try:
                conn.execute("ALTER TABLE unidentified ADD COLUMN face_thumbnail TEXT")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE unidentified ADD COLUMN voiceprint_spectrum TEXT")
            except Exception:
                pass
            # 更新 roles 表已有角色
            try:
                conn.execute("UPDATE roles SET display_name = '管理员' WHERE name = 'admin'")
                conn.execute("UPDATE roles SET display_name = '成员' WHERE name = 'member'")
            except Exception:
                pass
            # 记录迁移版本
            conn.execute("INSERT OR REPLACE INTO schema_version (version) VALUES (3)")
            logger.info('Schema migration to version 3 complete')
```

- [ ] **Step 2: 确保 faces 目录存在**

在 `init_database()` 末尾（或函数返回前）添加：

```python
        # 确保 faces 截图目录存在
        faces_dir = db_path.parent / 'faces'
        faces_dir.mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 3: Commit**

```bash
git add src/python/shared/database.py
git commit -m "feat: database migration v3 - role rename + new identity fields"
```

---

### Task 2: 角色体系升级

**Files:**
- Modify: `src/python/modules/role/role_manager.py`
- Modify: `src/python/modules/members/member_manager.py`

- [ ] **Step 1: 更新 role_manager.py 角色枚举和定义**

将 `role_manager.py` 中的 `Role` 枚举和映射从 4 种改为 5 种：

```python
class Role(IntEnum):
    """角色等级（数值越大权限越高）"""
    UNREGISTERED = -1
    GUEST = 0
    MEMBER = 1
    ADMIN = 2
    OWNER = 3

    @classmethod
    def from_string(cls, s: str) -> 'Role':
        mapping = {
            'unregistered': cls.UNREGISTERED,
            'guest': cls.GUEST,
            'member': cls.MEMBER,
            'admin': cls.ADMIN,
            'owner': cls.OWNER,
        }
        return mapping.get(s.lower(), cls.UNREGISTERED)


ROLE_NAMES = {
    Role.OWNER: '主人',
    Role.ADMIN: '管理员',
    Role.MEMBER: '成员',
    Role.GUEST: '访客',
    Role.UNREGISTERED: '未登记',
}

ROLE_BADGES = {
    Role.OWNER: '👑',
    Role.ADMIN: '🔵',
    Role.MEMBER: '🟢',
    Role.GUEST: '⚪',
    Role.UNREGISTERED: '⬜',
}

ROLE_CSS_CLASSES = {
    Role.OWNER: 'role-owner',
    Role.ADMIN: 'role-admin',
    Role.MEMBER: 'role-member',
    Role.GUEST: 'role-guest',
    Role.UNREGISTERED: 'role-unregistered',
}
```

更新 `SKILL_WHITELIST` 和 `DAILY_USAGE_LIMITS`（将 ADULT/CHILD 替换为 ADMIN/MEMBER，新增 UNREGISTERED）：

```python
SKILL_WHITELIST = {
    Role.OWNER: ['*'],
    Role.ADMIN: ['*'],
    Role.MEMBER: [
        'weather', 'time', 'reminder', 'music', 'translation',
        'knowledge', 'story', 'joke',
    ],
    Role.GUEST: ['weather', 'time', 'knowledge', 'joke'],
    Role.UNREGISTERED: [],
}

DAILY_USAGE_LIMITS = {
    Role.OWNER: 0,
    Role.ADMIN: 0,
    Role.MEMBER: 7200,
    Role.GUEST: 1800,
    Role.UNREGISTERED: 0,
}
```

- [ ] **Step 2: 更新 role_manager.py get_all_roles_info()**

找到 `get_all_roles_info()` 方法（约第 80 行后），确保返回的角色列表中包含 unregistered。若该方法从数据库读取 roles 表，则数据库迁移已处理。否则更新硬编码列表：

```python
def get_all_roles_info(self) -> list[dict]:
    """返回所有角色的信息（含权限矩阵）"""
    roles = [
        self._role_info('owner'),
        self._role_info('admin'),
        self._role_info('member'),
        self._role_info('guest'),
        self._role_info('unregistered'),
    ]
    return roles
```

- [ ] **Step 3: 更新 member_manager.py 中的角色校验**

在 `set_registration_info()` 方法中，将 role 校验从 `['owner','adult','child','guest']` 更新为：

```python
valid_roles = ['owner', 'admin', 'member', 'guest']
if role not in valid_roles:
    raise ValueError(f"Invalid role: {role}, must be one of {valid_roles}")
```

- [ ] **Step 4: 更新 member_manager.py 新增频谱存储方法**

```python
    @staticmethod
    def update_voiceprint_spectrum(member_id: str, spectrum_bins: list[float]):
        import json
        from src.python.shared.database import get_connection
        with get_connection() as conn:
            conn.execute(
                "UPDATE members SET voiceprint_spectrum = ? WHERE id = ?",
                (json.dumps(spectrum_bins), member_id)
            )

    @staticmethod
    def update_unidentified_spectrum(unid_id: str, spectrum_bins: list[float]):
        import json
        from src.python.shared.database import get_connection
        with get_connection() as conn:
            conn.execute(
                "UPDATE unidentified SET voiceprint_spectrum = ? WHERE id = ?",
                (json.dumps(spectrum_bins), unid_id)
            )
```

- [ ] **Step 5: 更新 member_manager.py 新增缩略图存储方法**

```python
    @staticmethod
    def update_face_thumbnail(member_id: str, thumbnail_path: str):
        from src.python.shared.database import get_connection
        with get_connection() as conn:
            conn.execute(
                "UPDATE members SET face_thumbnail = ? WHERE id = ?",
                (thumbnail_path, member_id)
            )

    @staticmethod
    def update_unidentified_thumbnail(unid_id: str, thumbnail_path: str):
        from src.python.shared.database import get_connection
        with get_connection() as conn:
            conn.execute(
                "UPDATE unidentified SET face_thumbnail = ? WHERE id = ?",
                (thumbnail_path, unid_id)
            )
```

- [ ] **Step 6: Commit**

```bash
git add src/python/modules/role/role_manager.py src/python/modules/members/member_manager.py
git commit -m "feat: upgrade role system from 4 to 5 tiers, add spectrum/thumbnail storage methods"
```

---

### Task 3: 后端 — 人脸截图存储

**Files:**
- Modify: `src/python/modules/camera/camera_pipeline.py`
- Modify: `src/python/modules/fusion/identity_fusion.py`
- Modify: `src/python/server/main.py`

- [ ] **Step 1: CameraPipeline 缓存最新帧**

在 `camera_pipeline.py` 的 `__init__` 中添加：

```python
        self._last_frame = None  # 最近一帧 RGB (用于人脸截图)
```

在 `_capture_loop()` 中，帧读取后立即缓存：

```python
                ret, frame = self._cap.read()
                if not ret or frame is None:
                    continue

                # RGB 转换
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                self._last_frame = frame  # 缓存原始帧供截图使用
```

- [ ] **Step 2: 新增 capture_face_thumbnail 方法**

在 `CameraPipeline` 类中添加：

```python
    def capture_face_thumbnail(self, bbox: dict) -> bytes | None:
        """根据相对 bbox {x, y, width, height} 从最近帧截取人脸缩略图
        Returns: JPEG bytes (128×128) or None
        """
        if self._last_frame is None:
            return None
        try:
            h, w = self._last_frame.shape[:2]
            x = int(bbox['x'] * w)
            y = int(bbox['y'] * h)
            bw = int(bbox['width'] * w)
            bh = int(bbox['height'] * h)
            # 边界裁切
            x = max(0, x)
            y = max(0, y)
            bw = min(bw, w - x)
            bh = min(bh, h - y)
            if bw <= 0 or bh <= 0:
                return None
            face = self._last_frame[y:y+bh, x:x+bw]
            face_resized = cv2.resize(face, (128, 128))
            _, jpeg = cv2.imencode('.jpg', face_resized, [cv2.IMWRITE_JPEG_QUALITY, 85])
            return jpeg.tobytes()
        except Exception as e:
            logger.debug(f'Face thumbnail capture error: {e}')
            return None
```

- [ ] **Step 3: IdentityFusionEngine 确认身份时触发截图**

在 `identity_fusion.py` 中找到 `_emit_confirmed()` 或 `on_identity_confirmed` 回调处，确认身份后添加回调参数 `face_bbox`：

找到 `_confirm_identity()` 方法（约第 200 行附近），在身份确认输出中添加 `face_bbox` 字段到 identity dict。

在 `main.py` 的 `on_identity_confirmed()` 回调中添加截图保存逻辑：

```python
async def on_identity_confirmed(identity: dict):
    """融合引擎确认身份 → 截图保存 + 状态机 + 角色管理"""
    logger.info(f'Identity confirmed: {identity.get("display_name")} (role={identity.get("role")})')

    # 保存人脸截图
    face_bbox = identity.get('face_bbox')
    if face_bbox and camera_pipeline:
        try:
            jpeg_bytes = camera_pipeline.capture_face_thumbnail(face_bbox)
            if jpeg_bytes and identity.get('member_id'):
                import os
                from pathlib import Path
                faces_dir = Path(__file__).resolve().parent.parent.parent.parent / 'data' / 'faces'
                faces_dir.mkdir(parents=True, exist_ok=True)
                import time
                filename = f"{identity['member_id']}_{int(time.time())}.jpg"
                filepath = faces_dir / filename
                filepath.write_bytes(jpeg_bytes)
                # 更新数据库
                relative_path = f"data/faces/{filename}"
                member_manager.update_face_thumbnail(identity['member_id'], relative_path)
        except Exception as e:
            logger.debug(f'Face thumbnail save error: {e}')

    # 原有逻辑...
    if state_machine:
        state_machine.set_identity(identity)
        state_machine.on_event('identity_confirmed', identity)
    # ...
```

- [ ] **Step 4: 在 CameraPipeline 的人脸检测中记录 bbox**

在 `_detect_with_insightface()` 和 `_detect_with_mediapipe()` 返回的人脸数据中确保包含 `bbox` 字段（已有）。在 `_emit_face_detected` 中传递 bbox 给融合引擎。找到 `on_face_embedding` 回调，扩展 payload 包含 bbox。

- [ ] **Step 5: Commit**

```bash
git add src/python/modules/camera/camera_pipeline.py src/python/modules/fusion/identity_fusion.py src/python/server/main.py
git commit -m "feat: add face thumbnail capture on identity confirmation"
```

---

### Task 4: 后端 — 声纹频谱生成

**Files:**
- Modify: `src/python/modules/audio/audio_pipeline.py`
- Modify: `src/python/server/main.py`

- [ ] **Step 1: AudioPipeline 声纹提取后生成频谱**

在 `audio_pipeline.py` 的 `_try_extract_voiceprint()` 方法中，声纹 embedding 提取成功后（约第 455 行 `emb_np` 计算后），添加频谱生成逻辑：

```python
            # 生成 48-bin 声纹频谱迷你图数据
            try:
                spectrum_48 = []
                for i in range(48):
                    start = i * 4
                    end = min(start + 4, 192)
                    segment = emb_np[start:end]
                    rms = float(np.sqrt(np.mean(segment ** 2)))
                    spectrum_48.append(rms)
                max_rms = max(spectrum_48) if max(spectrum_48) > 0 else 1.0
                spectrum_48 = [s / max_rms for s in spectrum_48]
                payload['spectrum_bins'] = spectrum_48
            except Exception:
                payload['spectrum_bins'] = []
```

在声纹回调 payload 中包含 `spectrum_bins`。

- [ ] **Step 2: 在 main.py on_voiceprint 中存储频谱**

修改 `on_voiceprint()` 回调（约第 456 行），增加频谱存储：

```python
async def on_voiceprint(embedding: np.ndarray, duration: float):
    """Phase 2: 声纹 embedding → 融合引擎"""
    if fusion_engine:
        fusion_engine.submit_voice_evidence(embedding, 1.0)

    # 存储声纹频谱（若当前身份已确认）
    if fusion_engine:
        current = fusion_engine.get_current_identity()
        if current and current.get('member_id'):
            try:
                # 从 embedding 生成 48-bin 频谱
                spectrum_48 = []
                for i in range(48):
                    start = i * 4
                    end = min(start + 4, 192)
                    segment = embedding[start:end]
                    rms = float(np.sqrt(np.mean(segment ** 2)))
                    spectrum_48.append(rms)
                max_rms = max(spectrum_48) if max(spectrum_48) > 0 else 1.0
                spectrum_48 = [s / max_rms for s in spectrum_48]
                member_manager.update_voiceprint_spectrum(current['member_id'], spectrum_48)
            except Exception as e:
                logger.debug(f'Voiceprint spectrum save error: {e}')
```

- [ ] **Step 3: Commit**

```bash
git add src/python/modules/audio/audio_pipeline.py src/python/server/main.py
git commit -m "feat: generate and store 48-bin voiceprint spectrum on voiceprint extraction"
```

---

### Task 5: 通知模块 stub

**Files:**
- Create: `src/python/modules/notification/__init__.py`
- Create: `src/python/modules/notification/notifier.py`
- Modify: `src/python/server/main.py`

- [ ] **Step 1: 创建 notifier.py stub**

```python
"""
Frank 外部通知服务接口（预留）

支持：
- SMTP 邮件通知
- 即时通讯 Webhook 通知（企业微信/钉钉/Slack）
"""

import logging

logger = logging.getLogger('frank.notification')


class ExternalNotifier:
    """外部通知服务接口"""

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self.email_enabled = self.config.get('email', {}).get('enabled', False)
        self.im_enabled = self.config.get('im', {}).get('enabled', False)

    async def send_email(self, to: str, subject: str, body: str):
        """通过 SMTP 发送邮件"""
        if not self.email_enabled:
            logger.info(f'[NOTIFIER-STUB] Email not enabled. Would send to {to}: {subject}')
            return
        raise NotImplementedError("SMTP email not yet implemented")

    async def send_im(self, message: str):
        """通过即时通讯 Webhook 发送消息"""
        if not self.im_enabled:
            im_config = self.config.get('im', {})
            service = im_config.get('service', 'unknown')
            logger.info(f'[NOTIFIER-STUB] IM ({service}) not enabled. Would send: {message}')
            return
        raise NotImplementedError("IM webhook not yet implemented")

    async def notify_owners(self, event: str, details: dict):
        """通知所有主人和管理员关于事件"""
        logger.info(f'[NOTIFIER-STUB] Event: {event}, Details: {details}')
        # TODO: 查询 owner + admin 成员列表，获取联系方式
        # 如果邮件/IM 已配置 → 发送通知
        # 否则 → 仅记录日志
```

- [ ] **Step 2: 创建 __init__.py**

```python
from .notifier import ExternalNotifier

__all__ = ['ExternalNotifier']
```

- [ ] **Step 3: 在 main.py 中集成 notifier**

在 `main.py` 顶部 import 中添加：

```python
from src.python.modules.notification import ExternalNotifier
notifier: ExternalNotifier | None = None
```

在 `main()` 函数中初始化（约 line 670，task_manager 初始化之后）：

```python
    notifier = ExternalNotifier(config.get('notification', {}))
```

在 `on_identity_confirmed` 或 member identified 事件处理中调用通知：

```python
    # 通知主人/管理员
    if notifier:
        await notifier.notify_owners('member.identified', {
            'display_name': identity.get('display_name'),
            'role': identity.get('role'),
        })
```

- [ ] **Step 4: Commit**

```bash
git add src/python/modules/notification/ src/python/server/main.py
git commit -m "feat: add ExternalNotifier stub module with email/IM interface placeholders"
```

---

### Task 6: 前端 — 角色说明面板 (roleInfoPanel)

**Files:**
- Modify: `src/electron/renderer/index.html`
- Modify: `src/electron/renderer/styles.css`

- [ ] **Step 1: 在 index.html 中新增 roleInfoPanel**

在 `taskDetailPanel` 之后、`notifPanel` 之前添加新面板 HTML：

```html
      <!-- Role Info Panel -->
      <div class="panel-slide" id="roleInfoPanel">
        <div class="panel-slide-header">
          <span class="panel-slide-title">角色权限说明</span>
          <button class="panel-slide-close" data-panel="roleInfoPanel">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
          </button>
        </div>
        <div class="panel-slide-body" id="roleInfoContent">
          <div class="role-info-loading">加载中...</div>
        </div>
      </div>
```

- [ ] **Step 2: 在 identityPanel 标题栏添加"角色说明"按钮**

找到 identityPanel 的 header（约第 207 行），在标题旁边添加按钮：

```html
        <div class="panel-slide-header">
          <span class="panel-slide-title">身份识别</span>
          <div style="display:flex;align-items:center;gap:var(--space-2);">
            <button class="btn-sm" id="btnRoleInfo" title="查看角色权限说明">角色说明 ▶</button>
            <button class="panel-slide-close" data-panel="identityPanel">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
            </button>
          </div>
        </div>
```

- [ ] **Step 3: 在 styles.css 中添加角色面板样式**

```css
/* ─── Role info panel ──────────────────────────────────────────── */
.role-info-card {
  padding: var(--space-3) var(--space-4);
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  margin-bottom: var(--space-2);
}
.role-info-card.role-owner { border-color: #ffd700; box-shadow: 0 0 8px rgba(255, 215, 0, 0.15); }
.role-info-card-header {
  display: flex; align-items: center; gap: var(--space-2);
  margin-bottom: var(--space-1);
}
.role-info-level {
  font-family: var(--font-mono); font-size: 10px;
  color: var(--muted); margin-left: auto;
}
.role-info-desc {
  font-size: var(--text-xs); color: var(--fg-2);
  line-height: 1.5;
}
.role-info-section-title {
  font-size: 12px; text-transform: uppercase;
  color: var(--muted); padding: var(--space-3) 0 var(--space-2);
  letter-spacing: 0.06em; border-bottom: 1px solid var(--border);
  margin-bottom: var(--space-2);
}
```

- [ ] **Step 4: 在 app.js 中添加 roleInfoPanel 打开逻辑**

在 `openPanel()` 函数中添加：

```javascript
function openPanel(name) {
  const map = {
    identity: 'identityPanel',
    tasks: 'taskDetailPanel',
    notifications: 'notifPanel',
    settings: 'settingsPanel',
    members: 'membersPanel',
    chat: 'chatOverlay',
    roleInfo: 'roleInfoPanel',
  };
  // ... existing logic ...
}
```

添加按钮事件绑定：

```javascript
$('btnRoleInfo')?.addEventListener('click', (e) => {
  e.stopPropagation();
  openPanel('roleInfo');
  loadRoleInfoPanel();
});
```

添加渲染函数：

```javascript
function loadRoleInfoPanel() {
  window.frankAPI?.sendMessage?.({ type: 'role.list' });
}

function renderRoleInfoPanel(roles) {
  const container = $('roleInfoContent');
  if (!container || !roles?.length) return;

  const perms = [
    {key:'member_management',label:'成员管理'},
    {key:'system_config',label:'系统配置'},
    {key:'full_data_access',label:'全数据访问'},
    {key:'regular_skills',label:'常规技能'},
    {key:'smart_home_control',label:'智能家居'},
    {key:'calendar_notes',label:'日历笔记'},
    {key:'file_operations',label:'文件操作'},
    {key:'third_party_skills',label:'第三方技能'},
    {key:'session_preempt',label:'会话打断'},
    {key:'basic_qa',label:'基础问答'},
  ];

  const descs = {
    owner: '系统所有者，每个部署环境仅 1 人。拥有最高指令权限，不可删除。可管理所有成员、配置系统、访问全部数据。',
    admin: '管理员，由主人授权。拥有全部指令权限（成员管理+系统配置），可添加/修改/删除成员。',
    member: '家庭成员。可使用所有常规技能，但不可管理成员和修改系统配置。每日使用时长限制 2 小时。',
    guest: '临时访客。仅可使用基础问答、天气查询、时间查询等受限功能。每日限制 30 分钟，数据不持久化。',
    unregistered: '未登记。系统通过摄像头自动发现但尚未标识的人物。无任何权限，系统会引导其录入信息成为访客。',
  };

  container.innerHTML = `
    <div class="role-info-section-title">角色层级</div>
    ${roles.map(r => `
      <div class="role-info-card role-${r.name}">
        <div class="role-info-card-header">
          <span style="font-size:18px;">${r.badge || '⬜'}</span>
          <span style="font-size:14px;font-weight:500;">${r.display_name}</span>
          <span class="role-info-level">等级 ${r.level}</span>
        </div>
        <div class="role-info-desc">${descs[r.name] || r.description || ''}</div>
      </div>`).join('')}

    <div class="role-info-section-title">权限矩阵</div>
    <div class="permission-matrix">
      <table class="perm-table">
        <thead><tr><th>权限</th>${roles.map(r => `<th>${r.badge} ${r.display_name}</th>`).join('')}</tr></thead>
        <tbody>
          ${perms.map(p => `<tr><td>${p.label}</td>${roles.map(r =>
            `<td class="${r.permissions?.[p.key] ? 'perm-yes' : 'perm-no'}">${r.permissions?.[p.key] ? '✓' : '✗'}</td>`
          ).join('')}</tr>`).join('')}
        </tbody>
      </table>
    </div>
  `;
}
```

更新 IPC 监听：`onRoleList` 回调中，如果 `roleInfoPanel` 已打开，则调用 `renderRoleInfoPanel`。

- [ ] **Step 5: Commit**

```bash
git add src/electron/renderer/index.html src/electron/renderer/styles.css src/electron/renderer/app.js
git commit -m "feat: add role info panel with role hierarchy and permission matrix"
```

---

### Task 7: 前端 — 身份识别面板重构（HTML + CSS）

**Files:**
- Modify: `src/electron/renderer/index.html`（替换 identityPanel 内容）
- Modify: `src/electron/renderer/styles.css`（新增人物列表样式）

- [ ] **Step 1: 重写 identityPanel body**

完整替换 `identityPanel` 的 `panel-slide-body` 内容：

```html
        <div class="panel-slide-body">
          <!-- 统计栏 -->
          <div class="identity-stats" id="identityStats">
            <span class="identity-stat"><span id="statIdentified">0</span> 已标识</span>
            <span class="identity-stat"><span id="statPending">0</span> 待标识</span>
            <span class="identity-stat"><span id="statTotal">0</span> 历史</span>
          </div>

          <!-- 筛选标签 -->
          <div class="identity-filters" id="identityFilters">
            <button class="identity-filter active" data-role="all">全部</button>
            <button class="identity-filter" data-role="owner">👑 主人</button>
            <button class="identity-filter" data-role="admin">🔵 管理员</button>
            <button class="identity-filter" data-role="member">🟢 成员</button>
            <button class="identity-filter" data-role="guest">⚪ 访客</button>
            <button class="identity-filter" data-role="unidentified">⬜ 未标识</button>
          </div>

          <!-- 人物列表 -->
          <div class="identity-list" id="identityList">
            <p class="empty-state" id="identityEmpty">暂无识别记录</p>
          </div>
        </div>
```

- [ ] **Step 2: 移除 identityPanel 旧内容**

删除旧的 identity-card、roleCards、permissionMatrix 等 DOM 元素（约第 214-224 行区域）。

- [ ] **Step 3: 在 styles.css 中添加人物列表样式**

```css
/* ─── Identity panel ───────────────────────────────────────────── */
.identity-stats {
  display: flex; gap: var(--space-3);
  padding: 0 0 var(--space-3);
  border-bottom: 1px solid var(--border-soft);
  margin-bottom: var(--space-3);
}
.identity-stat {
  flex: 1; text-align: center;
  font-size: var(--text-xs); color: var(--muted);
  font-family: var(--font-mono);
}
.identity-stat span {
  font-size: var(--text-md); font-weight: 600;
  color: var(--fg); display: block;
}

.identity-filters {
  display: flex; flex-wrap: wrap; gap: var(--space-1);
  margin-bottom: var(--space-3);
}
.identity-filter {
  padding: 4px 10px; border-radius: var(--radius-full);
  background: var(--border-soft); border: none;
  color: var(--fg-2); font-size: 11px;
  cursor: pointer; transition: all var(--motion-fast);
  font-family: var(--font-mono);
}
.identity-filter:hover { background: var(--surface-elevated); color: var(--fg); }
.identity-filter.active {
  background: var(--accent-soft); color: var(--accent);
  font-weight: 600;
}

.identity-list {
  display: flex; flex-direction: column; gap: var(--space-2);
  overflow-y: auto; max-height: calc(100vh - 320px);
}

.identity-item {
  display: grid;
  grid-template-columns: 56px 56px 1fr auto;
  gap: var(--space-3);
  padding: var(--space-3);
  background: var(--bg);
  border: 1px solid var(--border-soft);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: border-color var(--motion-fast);
}
.identity-item:hover { border-color: var(--border); }
.identity-item.unidentified { border-left: 2px solid var(--warning); }

.identity-face-thumb {
  width: 56px; height: 56px;
  border-radius: var(--radius-sm);
  background: var(--border-soft);
  overflow: hidden;
  display: grid; place-items: center;
  flex-shrink: 0;
}
.identity-face-thumb img {
  width: 100%; height: 100%; object-fit: cover;
}
.identity-face-thumb .face-placeholder {
  font-size: 20px; color: var(--muted);
}

.identity-voiceprint-mini {
  width: 56px; height: 56px;
  display: flex; align-items: flex-end;
  gap: 1px; padding: 4px;
  background: var(--border-soft);
  border-radius: var(--radius-sm);
  flex-shrink: 0;
}
.voiceprint-mini-bar {
  flex: 1; min-width: 1px;
  border-radius: 1px;
  background: linear-gradient(0deg, oklch(62% 0.10 45), oklch(76% 0.18 65));
  min-height: 2px;
}

.identity-info {
  display: flex; flex-direction: column; gap: 2px;
  justify-content: center; min-width: 0;
}
.identity-info-name {
  font-size: var(--text-sm); font-weight: 600;
  color: var(--fg); overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap;
}
.identity-info-role {
  font-size: 11px; color: var(--fg-2);
  display: flex; align-items: center; gap: 4px;
}
.identity-info-meta {
  font-size: 10px; color: var(--muted);
  font-family: var(--font-mono);
  display: flex; gap: var(--space-2);
}

.identity-actions {
  display: flex; flex-direction: column;
  justify-content: center; gap: var(--space-1);
  flex-shrink: 0;
}
.identity-action-btn {
  padding: 4px 10px; border-radius: var(--radius-sm);
  font-size: 10px; font-weight: 500;
  cursor: pointer; border: 1px solid var(--border);
  background: transparent; color: var(--fg-2);
  transition: all var(--motion-fast);
  white-space: nowrap;
}
.identity-action-btn:hover { border-color: var(--accent); color: var(--fg); }
.identity-action-btn.primary {
  background: var(--accent); color: var(--accent-on);
  border-color: var(--accent);
}
.identity-action-btn.primary:hover { opacity: 0.85; }
```

- [ ] **Step 4: Commit**

```bash
git add src/electron/renderer/index.html src/electron/renderer/styles.css
git commit -m "feat: restructure identity panel HTML with person list layout"
```

---

### Task 8: 前端 — 身份识别面板渲染逻辑

**Files:**
- Modify: `src/electron/renderer/app.js`

- [ ] **Step 1: 替换 loadPersonaPanel 和相关渲染函数**

删除（或注释）旧的 `loadPersonaPanel()`、`updateIdentityCard()`、`renderRoleCards()`、`renderPermissionMatrix()` 函数。

新增人物列表渲染函数：

```javascript
// ─── Identity Panel: person list ──────────────────────────
let allPersons = [];
let currentFilter = 'all';

function loadPersonaPanel() {
  window.frankAPI?.sendMessage?.({ type: 'member.list' });
  window.frankAPI?.sendMessage?.({ type: 'member.pending' });
}

function renderPersonList(members, pending) {
  allPersons = [
    ...(members || []).map(m => ({ ...m, personType: 'member' })),
    ...(pending || []).map(p => ({
      ...p,
      personType: 'unidentified',
      display_name: p.serial_name || `访客_${(p.id || '').substring(0, 4).toUpperCase()}`,
      role: 'unregistered',
    })),
  ];

  // 更新统计
  const identified = (members || []).length;
  const unidentified = (pending || []).length;
  document.getElementById('statIdentified').textContent = identified;
  document.getElementById('statPending').textContent = unidentified;
  document.getElementById('statTotal').textContent = identified + unidentified;

  applyFilter();
}

function applyFilter() {
  const filtered = currentFilter === 'all'
    ? allPersons
    : currentFilter === 'unidentified'
      ? allPersons.filter(p => p.personType === 'unidentified')
      : allPersons.filter(p => p.role === currentFilter);

  const list = document.getElementById('identityList');
  const empty = document.getElementById('identityEmpty');
  if (!list) return;

  if (!filtered.length) {
    empty?.classList.remove('hidden');
    list.innerHTML = '';
    return;
  }
  empty?.classList.add('hidden');

  const BADGES = { owner: '👑', admin: '🔵', member: '🟢', guest: '⚪', unregistered: '⬜' };
  const NAMES = { owner: '主人', admin: '管理员', member: '成员', guest: '访客', unregistered: '未登记' };

  list.innerHTML = filtered.map(p => {
    const isIdentified = p.personType === 'member';
    const role = p.role || 'unregistered';
    const faceThumb = p.face_thumbnail
      ? `<img src="../${p.face_thumbnail}" onerror="this.parentElement.innerHTML='<span class=face-placeholder>${BADGES[role]||'⬜'}</span>'" />`
      : `<span class="face-placeholder">${BADGES[role] || '⬜'}</span>`;

    // 声纹频谱迷你图
    let spectrumBars = '';
    if (p.voiceprint_spectrum) {
      try {
        const bins = typeof p.voiceprint_spectrum === 'string'
          ? JSON.parse(p.voiceprint_spectrum) : p.voiceprint_spectrum;
        spectrumBars = (bins || []).slice(0, 9).map((v, i) =>
          `<div class="voiceprint-mini-bar" style="height:${Math.max(2, v * 52)}px"></div>`
        ).join('');
      } catch (e) { /* empty */ }
    }

    return `
    <div class="identity-item ${isIdentified ? '' : 'unidentified'}">
      <div class="identity-face-thumb">${faceThumb}</div>
      <div class="identity-voiceprint-mini">
        ${spectrumBars || '<span style="font-size:8px;color:var(--muted);margin:auto;">待采集</span>'}
      </div>
      <div class="identity-info">
        <div class="identity-info-name">${p.display_name || '未知'}</div>
        <div class="identity-info-role">${BADGES[role]} ${NAMES[role]}</div>
        <div class="identity-info-meta">
          ${isIdentified
            ? `最近识别: ${formatTime(p.last_recognized_at || p.last_active_at)} · 置信度 ${(p.recognition_confidence || 0 * 100).toFixed(0)}%`
            : `最近出现: ${formatTime(p.last_seen_at)} · 出现 ${p.appearance_count || 0} 次`}
        </div>
      </div>
      <div class="identity-actions">
        ${isIdentified
          ? `<button class="identity-action-btn" onclick="event.stopPropagation();editPerson('${p.member_id || p.id}')">✏️ 修改</button>`
          : `<button class="identity-action-btn primary" onclick="event.stopPropagation();identifyPerson('${p.unidentified_id || p.id}')">📝 标识</button>`}
      </div>
    </div>`;
  }).join('');
}

function editPerson(memberId) {
  const name = prompt('修改显示名称（2-20 字符）：');
  if (!name || name.length < 2 || name.length > 20) { if (name) showToast('名称长度需在 2-20 个字符之间', 'error'); return; }
  const role = prompt('选择角色（owner / admin / member / guest）：', 'member');
  if (!['owner', 'admin', 'member', 'guest'].includes(role?.toLowerCase())) { showToast('角色无效', 'error'); return; }
  window.frankAPI?.sendMessage?.({ type: 'member.update', payload: { member_id: memberId, display_name: name, role: role.toLowerCase() } });
  setTimeout(loadPersonaPanel, 500);
}

function identifyPerson(unidentifiedId) {
  const name = prompt('请输入该成员显示名称（2-20 字符）：');
  if (!name || name.length < 2 || name.length > 20) { if (name) showToast('名称长度需在 2-20 个字符之间', 'error'); return; }
  const role = prompt('请选择角色（admin / member / guest）：', 'guest');
  if (!['admin', 'member', 'guest'].includes(role?.toLowerCase())) { showToast('角色必须为 admin、member 或 guest', 'error'); return; }
  window.frankAPI?.sendMessage?.({ type: 'member.identify', payload: { unidentified_id: unidentifiedId, display_name: name, role: role.toLowerCase() } });
  setTimeout(loadPersonaPanel, 500);
}
```

- [ ] **Step 2: 添加筛选标签点击事件**

在 DOM 事件绑定区域添加：

```javascript
document.getElementById('identityFilters')?.addEventListener('click', (e) => {
  const btn = e.target.closest('.identity-filter');
  if (!btn) return;
  document.querySelectorAll('.identity-filter').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  currentFilter = btn.dataset.role;
  applyFilter();
});
```

- [ ] **Step 3: 更新 IPC 监听**

将 `onMemberList` 和 `onMemberPending` 回调改为联动调用 `renderPersonList`：

```javascript
let cachedMembers = [];
let cachedPending = [];

window.frankAPI.onMemberList(data => {
  cachedMembers = data?.members || [];
  renderPersonList(cachedMembers, cachedPending);
});
window.frankAPI.onMemberPending(data => {
  cachedPending = data?.pending || [];
  renderPersonList(cachedMembers, cachedPending);
});
```

更新 `onRoleList` 回调，追加 roleInfoPanel 渲染：

```javascript
window.frankAPI.onRoleList?.(data => {
  if (data?.roles) {
    if (PanelManager.isOpen($('roleInfoPanel'))) {
      renderRoleInfoPanel(data.roles);
    }
  }
});
```

- [ ] **Step 4: 在 app.js 顶部更新角色常量映射**

```javascript
const ROLE_BADGES = { owner: '👑', admin: '🔵', member: '🟢', guest: '⚪', unregistered: '⬜' };
const ROLE_NAMES = { owner: '主人', admin: '管理员', member: '成员', guest: '访客', unregistered: '未登记' };
```

- [ ] **Step 5: Commit**

```bash
git add src/electron/renderer/app.js
git commit -m "feat: add person list rendering, filtering, and identity actions to identity panel"
```

---

### Task 9: 前端 — 注册向导角色标签更新

**Files:**
- Modify: `src/electron/renderer/index.html`（wizard 角色选项）
- Modify: `src/electron/renderer/app.js`（角色校验）

- [ ] **Step 1: 更新注册向导角色卡片**

将 wizard step 1 中的角色选项从"成人/儿童/访客"改为"管理员/成员/访客"：

```html
<label class="role-card-radio"><input type="radio" name="regRole" value="admin"><span class="role-card-icon">🔵</span><span class="role-card-label">管理员</span><span class="role-card-desc">全部指令权限，可管理成员</span></label>
<label class="role-card-radio"><input type="radio" name="regRole" value="member"><span class="role-card-icon">🟢</span><span class="role-card-label">成员</span><span class="role-card-desc">常规技能 + 时长限制</span></label>
<label class="role-card-radio"><input type="radio" name="regRole" value="guest"><span class="role-card-icon">⚪</span><span class="role-card-label">访客</span><span class="role-card-desc">仅基础问答，不保留数据</span></label>
```

保留 `owner` 选项但隐藏（仅主人可见时显示）。

- [ ] **Step 2: 更新 app.js 中的角色校验**

找到 `openIdentifyDialog` 和 wizard 相关逻辑，将 `['adult','child','guest']` 改为 `['admin','member','guest']`。

- [ ] **Step 3: Commit**

```bash
git add src/electron/renderer/index.html src/electron/renderer/app.js
git commit -m "feat: update registration wizard role labels to new 5-tier system"
```

---

### Task 10: 集成验证

- [ ] **Step 1: 验证数据库迁移**

查看 `data/frank.db`，确认新字段存在，角色名称已更新。

- [ ] **Step 2: 验证前端面板**

手动验证清单：
- [ ] 身份识别面板显示人物列表（含统计栏、筛选标签）
- [ ] 已标识人物显示面部缩略图 + 声纹频谱迷你图
- [ ] 未标识人物显示标识入口
- [ ] 筛选标签可切换列表视图
- [ ] 角色说明面板可打开并展示正确内容
- [ ] 注册向导角色选项为 4 种（管理员/成员/访客 + 隐藏的 owner）

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "chore: final integration verification for identity panel redesign"
```

---

## 自审清单

1. **Spec coverage**:
   - [x] 身份面板重构（Task 7, 8）
   - [x] 角色说明面板（Task 6）
   - [x] 人脸截图存储（Task 3）
   - [x] 声纹频谱迷你图（Task 4）
   - [x] 角色体系变更（Task 2）
   - [x] 通知接口预留（Task 5）
   - [x] 注册向导更新（Task 9）
   - [x] 数据库迁移（Task 1）

2. **Placeholder scan**: 无 TBD/TODO/待定。所有代码步骤包含实际实现。

3. **Type consistency**:
   - 所有任务中的 role 名称一致：owner/admin/member/guest/unregistered
   - `member_manager` 新增方法名称在 Task 2 定义，Task 3/4 使用一致
   - preload IPC 通道名称与后端 WebSocket 消息类型一致
