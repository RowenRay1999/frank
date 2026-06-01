# 成员管理独立页面 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将身份识别面板的"添加成员"按钮改为成员管理页面入口，新建全窗口成员管理视图（列表+统计+操作栏），含详情模态和历史记录查看。

**Architecture:** 单 HTML 文件视图切换模式 — `#memberManagementView` 与 `.main-stage` 平级，通过 JS `navigateTo()` 控制显隐。后端新增 `member.stats` / `member.info` / `member.history` / `member.update` 四条 WS 路由，数据库新建 `command_history` 表。

**Tech Stack:** Vanilla JS (no framework), Python FastAPI-alike WS server, SQLite, oklch CSS design tokens

---

### Task 1: 数据库 — 新建 `command_history` 表 + Schema v4 迁移

**Files:**
- Modify: `src/python/shared/database.py:31,147-237`

- [ ] **Step 1: 更新 SCHEMA_VERSION 并新增 v4 迁移逻辑**

将 `SCHEMA_VERSION = 3` 改为 `SCHEMA_VERSION = 4`。在 `init_db()` 中 `if current_version < 3:` 块之后新增 `if current_version < 4:` 迁移块：

```python
# src/python/shared/database.py

# Line 31: 修改
SCHEMA_VERSION = 4

# 在 init_db() 中 if current_version < 3: 块结束（约 line 230 之后）、
# if current_version < SCHEMA_VERSION: 之前，插入新迁移块：
        if current_version < 4:
            logger.info('Running schema migration to version 4 (command_history)...')
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS command_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        member_id TEXT NOT NULL,
                        type TEXT NOT NULL CHECK(type IN ('conversation', 'task')),
                        timestamp TEXT NOT NULL DEFAULT (datetime('now')),
                        summary TEXT NOT NULL DEFAULT '',
                        detail TEXT NOT NULL DEFAULT '',
                        FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE
                    )
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_cmd_history_member
                    ON command_history(member_id, timestamp)
                """)
            except Exception as e:
                logger.warning(f'Schema v4 migration partially failed: {e}')
```

- [ ] **Step 2: 新增 `get_member_by_id()` 查询函数**

在 `list_all_members()` 函数之后（约 line 370）新增：

```python
def get_member_by_id(member_id: str) -> dict | None:
    """按 ID 查询单成员（JSON 安全：排除 BLOB 列）"""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM members WHERE id = ?", (member_id,)
        ).fetchone()
    if row is None:
        return None
    return _row_to_json_dict(row)
```

- [ ] **Step 3: 新增 `get_member_history()` 查询函数**

在 `get_member_by_id()` 之后新增：

```python
def get_member_history(member_id: str, max_age_days: int | None = None) -> list[dict]:
    """查询成员的指令历史记录
    
    Args:
        member_id: 成员 ID
        max_age_days: 最大保留天数，None 表示无限期
    """
    with get_connection() as conn:
        if max_age_days is not None:
            rows = conn.execute(
                """SELECT id, member_id, type, timestamp, summary, detail
                   FROM command_history
                   WHERE member_id = ? 
                     AND timestamp >= datetime('now', ?)
                   ORDER BY timestamp DESC""",
                (member_id, f'-{max_age_days} days')
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT id, member_id, type, timestamp, summary, detail
                   FROM command_history
                   WHERE member_id = ?
                   ORDER BY timestamp DESC""",
                (member_id,)
            ).fetchall()
    return [dict(r) for r in rows]
```

- [ ] **Step 4: 新增 `insert_command_history()` 写入函数**

在 `get_member_history()` 之后新增：

```python
def insert_command_history(member_id: str, cmd_type: str, summary: str, detail: str = ''):
    """写入一条指令历史记录"""
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO command_history (member_id, type, summary, detail)
               VALUES (?, ?, ?, ?)""",
            (member_id, cmd_type, summary, detail)
        )
```

- [ ] **Step 5: 新增 `get_member_stats()` 统计函数**

在 `insert_command_history()` 之后新增：

```python
def get_member_stats() -> dict:
    """获取成员统计信息"""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as c, COALESCE(SUM(appearance_count), 0) as total_visits FROM members WHERE labeled = 1"
        ).fetchone()
    return {
        'members_count': row['c'] if row else 0,
        'total_visits': row['total_visits'] if row else 0,
    }
```

- [ ] **Step 6: 验证**

运行 Python 确认导入无报错：

```bash
cd /e/docments/Frank && .venv/Scripts/python.exe -c "from src.python.shared.database import init_db, get_member_stats, get_member_history, insert_command_history, get_member_by_id; init_db(); print('DB init OK'); print(get_member_stats())"
```
Expected: `DB init OK` + `{'members_count': ..., 'total_visits': ...}`

- [ ] **Step 7: Commit**

```bash
git add src/python/shared/database.py
git commit -m "feat(database): 新增 command_history 表 + v4 迁移 + 统计/历史查询"
```

---

### Task 2: member_manager — 新增 stats / info / history 方法

**Files:**
- Modify: `src/python/modules/members/member_manager.py:88-290`

- [ ] **Step 1: 在 MemberManager 类中新增 `get_stats()` 静态方法**

在 `MemberManager.__init__()` 之后（约 line 92）新增：

```python
    @staticmethod
    def get_stats() -> dict:
        """获取成员统计：成员总数 + 总访问量"""
        from src.python.shared.database import get_member_stats
        return get_member_stats()
```

- [ ] **Step 2: 新增 `get_member_info()` 静态方法**

在 `get_stats()` 之后新增：

```python
    @staticmethod
    def get_member_info(member_id: str) -> dict | None:
        """获取单个成员完整信息"""
        from src.python.shared.database import get_member_by_id
        return get_member_by_id(member_id)
```

- [ ] **Step 3: 新增 `get_member_history()` 静态方法**

在 `get_member_info()` 之后新增：

```python
    @staticmethod
    def get_member_history(member_id: str, max_age_days: int | None = None) -> dict:
        """获取成员指令历史记录
        
        Args:
            member_id: 成员 ID
            max_age_days: 最大保留天数，None 表示无限期
        
        Returns:
            {'items': [{type, timestamp, summary, detail}, ...]}
        """
        from src.python.shared.database import get_member_history as db_get_history
        items = db_get_history(member_id, max_age_days)
        return {'items': items}
```

- [ ] **Step 4: 验证**

```bash
cd /e/docments/Frank && .venv/Scripts/python.exe -c "from src.python.modules.members.member_manager import MemberManager; s = MemberManager.get_stats(); print('Stats:', s); m = MemberManager.get_member_info if s['members_count'] > 0 else lambda x: None; print('OK')"
```
Expected: `Stats: {'members_count': ..., 'total_visits': ...}` + `OK`

- [ ] **Step 5: Commit**

```bash
git add src/python/modules/members/member_manager.py
git commit -m "feat(member_manager): 新增 get_stats / get_member_info / get_member_history 方法"
```

---

### Task 3: main.py — 新增 WS 路由 + 补全 member.update

**Files:**
- Modify: `src/python/server/main.py:203-251`

- [ ] **Step 1: 在 `member.delete` 处理之后新增 4 条路由**

在 `case 'member.delete':` 块结束（约 line 250）和 `# ── 身份查询` 注释（约 line 252）之间插入：

```python
            case 'member.update':
                if member_manager and payload.get('member_id'):
                    member_manager.update_member_info(
                        payload['member_id'],
                        display_name=payload.get('display_name'),
                        role=payload.get('role'))
                    updated = member_manager.get_member_info(payload['member_id'])
                    await send_message(websocket, 'member.updated', {'member': updated}, msg_id)
                else:
                    await send_error(websocket, 'MEM_NOT_INIT', '成员模块未初始化或缺少 member_id', True, '', msg_id)

            case 'member.stats':
                try:
                    stats = member_manager.get_stats() if member_manager else {}
                    await send_message(websocket, 'member.stats', stats, msg_id)
                except Exception as e:
                    logger.error(f'member.stats failed: {e}')
                    await send_error(websocket, 'STATS_FAILED', str(e), True, '', msg_id)

            case 'member.info':
                try:
                    if not member_manager or not payload.get('member_id'):
                        await send_error(websocket, 'BAD_REQUEST', '缺少 member_id', True, '', msg_id)
                        return
                    info = member_manager.get_member_info(payload['member_id'])
                    if info is None:
                        await send_error(websocket, 'NOT_FOUND', f'成员不存在: {payload["member_id"]}', True, '', msg_id)
                        return
                    await send_message(websocket, 'member.info', {'member': info}, msg_id)
                except Exception as e:
                    logger.error(f'member.info failed: {e}')
                    await send_error(websocket, 'INFO_FAILED', str(e), True, '', msg_id)

            case 'member.history':
                try:
                    if not member_manager or not payload.get('member_id'):
                        await send_error(websocket, 'BAD_REQUEST', '缺少 member_id', True, '', msg_id)
                        return
                    info = member_manager.get_member_info(payload['member_id'])
                    if info is None:
                        await send_error(websocket, 'NOT_FOUND', f'成员不存在: {payload["member_id"]}', True, '', msg_id)
                        return
                    role = info.get('role', 'guest')
                    days = None if role in ('owner', 'admin') else 120
                    history = member_manager.get_member_history(payload['member_id'], days)
                    await send_message(websocket, 'member.history', history, msg_id)
                except Exception as e:
                    logger.error(f'member.history failed: {e}')
                    await send_error(websocket, 'HISTORY_FAILED', str(e), True, '', msg_id)
```

- [ ] **Step 2: 验证语法**

```bash
cd /e/docments/Frank && .venv/Scripts/python.exe -c "import py_compile; py_compile.compile('src/python/server/main.py', doraise=True); print('Syntax OK')"
```
Expected: `Syntax OK`

- [ ] **Step 3: Commit**

```bash
git add src/python/server/main.py
git commit -m "feat(main): 新增 member.stats/info/history/update 四条 WS 路由"
```

---

### Task 4: HTML — 新增 memberManagementView + 两个模态 + 移除 membersPanel

**Files:**
- Modify: `src/electron/renderer/index.html:179-199,230-232,399`

- [ ] **Step 1: 移除 `#membersPanel`（line 179–199）**

删除整个 `<!-- Members Panel -->` 区块（从 `<div class="panel-slide" id="membersPanel">` 到 `</div>` 闭合标签）。

- [ ] **Step 2: 修改 `#btnAddMemberIdentity` 行为标记（line 181-183→修改后位置）**

当前 identityPanel 底部按钮保持结构不变，仅将 `onclick` 从 `openWizard()` 改为通过 app.js 事件监听绑定（见 Task 8），所以在此步**不修改**按钮 HTML，仅移除其旧的内联 onclick（如果存在）。确认 `#btnAddMemberIdentity` 按钮无内联 `onclick` 属性：

```html
<button class="btn-primary-full" id="btnAddMemberIdentity">＋ 成员管理</button>
```
（文案从"添加成员"改为"成员管理"，反映其新用途）

- [ ] **Step 3: 在 `.main-stage` 闭合 `</div>` 之后、wizard overlay 之前，新增 `#memberManagementView`**

在 `</div><!-- /main-stage -->`（约 line 307）之后插入：

```html
  <!-- ═══════════════════════════════════════════════════════════════
       Member Management View (full-window)
       ═══════════════════════════════════════════════════════════════ -->
  <div id="memberManagementView" class="member-mgmt-view hidden">
    <div class="member-mgmt-topbar">
      <button class="member-mgmt-back" id="btnMemberMgmtBack" title="返回主界面">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18"><path d="M15 18l-6-6 6-6"></path></svg>
      </button>
      <span class="member-mgmt-title">成员管理</span>
      <div class="member-mgmt-stats">
        <div class="member-mgmt-stat">
          <span class="member-mgmt-stat-value" id="statMembersCount">0</span>
          <span class="member-mgmt-stat-label">成员总数</span>
        </div>
        <div class="member-mgmt-stat">
          <span class="member-mgmt-stat-value" id="statTotalVisits">0</span>
          <span class="member-mgmt-stat-label">总访问量</span>
        </div>
      </div>
    </div>
    <div class="member-mgmt-list" id="memberMgmtList">
      <p class="empty-state" id="memberMgmtEmpty">暂无已标识成员</p>
    </div>
    <div class="member-mgmt-actionbar">
      <button class="btn-primary-full" id="btnMemberMgmtAdd">＋ 新增成员</button>
    </div>
  </div>

  <!-- Member Detail Modal -->
  <div id="memberDetailOverlay" class="member-detail-overlay hidden">
    <div class="member-detail-card">
      <div class="member-detail-header">
        <div class="member-detail-face" id="detailFace"></div>
        <div class="member-detail-identity">
          <span class="member-detail-name" id="detailName"></span>
          <span class="member-detail-role" id="detailRole"></span>
          <span class="member-detail-confidence" id="detailConfidence"></span>
        </div>
        <button class="panel-slide-close" id="btnDetailClose">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><path d="M18 6L6 18M6 6l12 12"></path></svg>
        </button>
      </div>
      <div class="member-detail-info">
        <div class="member-detail-info-row"><span class="detail-label">识别置信度</span><span id="detailRecogConfidence">—</span></div>
        <div class="member-detail-info-row"><span class="detail-label">注册时间</span><span id="detailCreatedAt">—</span></div>
        <div class="member-detail-info-row"><span class="detail-label">最后活跃</span><span id="detailLastActive">—</span></div>
        <div class="member-detail-info-row"><span class="detail-label">访问次数</span><span id="detailAppearanceCount">—</span></div>
      </div>
      <div class="member-detail-actions">
        <button class="btn-sm" id="btnDetailHistory">📋 查看历史指令记录</button>
        <button class="btn-sm" id="btnDetailEdit">✏️ 编辑信息</button>
        <button class="btn-sm" id="btnDetailDelete" style="color:var(--danger);border-color:var(--danger);">🗑 删除成员</button>
      </div>
    </div>
  </div>

  <!-- History Modal -->
  <div id="historyOverlay" class="history-overlay hidden">
    <div class="history-card">
      <div class="history-header">
        <span class="history-title" id="historyTitle">历史指令记录</span>
        <button class="panel-slide-close" id="btnHistoryClose">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><path d="M18 6L6 18M6 6l12 12"></path></svg>
        </button>
      </div>
      <div class="history-filter-bar" id="historyFilterBar">
        <button class="history-filter active" data-type="all">全部</button>
        <button class="history-filter" data-type="conversation">💬 对话</button>
        <button class="history-filter" data-type="task">📋 任务</button>
      </div>
      <div class="history-timeline" id="historyTimeline">
        <p class="empty-state" id="historyEmpty">暂无历史记录</p>
      </div>
    </div>
  </div>
```

- [ ] **Step 4: Commit**

```bash
git add src/electron/renderer/index.html
git commit -m "feat(html): 新增成员管理视图 + 详情模态 + 历史模态；移除 membersPanel"
```

---

### Task 5: CSS — 新增成员管理页 + 模态样式

**Files:**
- Modify: `src/electron/renderer/styles.css`（在现有样式之后追加）

- [ ] **Step 1: 在文件末尾追加成员管理视图样式**

```css
/* ═══════════════════════════════════════════════════════════════════
   成员管理独立页面
   ═══════════════════════════════════════════════════════════════════ */
.member-mgmt-view {
  position: absolute; inset: 0; z-index: 50;
  display: flex; flex-direction: column;
  background: var(--bg);
}
.member-mgmt-view.hidden { display: none; }

/* 顶部栏 */
.member-mgmt-topbar {
  display: flex; align-items: center; gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  background: var(--surface-glass);
  backdrop-filter: blur(12px);
}
.member-mgmt-back {
  display: flex; align-items: center; justify-content: center;
  width: 32px; height: 32px; border-radius: var(--radius-sm);
  border: 1px solid var(--border); background: transparent;
  color: var(--fg-2); cursor: pointer;
  transition: all var(--motion-fast);
  flex-shrink: 0;
}
.member-mgmt-back:hover { border-color: var(--accent); color: var(--fg); }
.member-mgmt-title {
  font-size: 16px; font-weight: 600; color: var(--fg);
  flex: 1;
}
.member-mgmt-stats {
  display: flex; gap: var(--space-4); flex-shrink: 0;
}
.member-mgmt-stat {
  display: flex; flex-direction: column; align-items: center;
  gap: 2px;
}
.member-mgmt-stat-value {
  font-size: 18px; font-weight: 700; color: var(--accent);
  font-family: var(--font-mono);
}
.member-mgmt-stat-label {
  font-size: 10px; color: var(--muted); text-transform: uppercase;
  letter-spacing: 0.05em;
}

/* 成员列表 */
.member-mgmt-list {
  flex: 1; overflow-y: auto; padding: var(--space-2) var(--space-3);
  display: flex; flex-direction: column; gap: var(--space-2);
}

/* 单条成员条目 */
.member-mgmt-item {
  display: grid;
  grid-template-columns: 48px 36px 1fr auto;
  gap: var(--space-2);
  padding: var(--space-2);
  background: var(--surface-glass);
  border: 1px solid var(--border-soft);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: border-color var(--motion-fast);
  align-items: center;
}
.member-mgmt-item:hover { border-color: var(--accent); }
.member-mgmt-face {
  width: 48px; height: 48px; border-radius: var(--radius-sm);
  background: var(--border-soft); overflow: hidden;
  display: grid; place-items: center; flex-shrink: 0;
}
.member-mgmt-face img {
  width: 100%; height: 100%; object-fit: cover;
}
.member-mgmt-face .face-placeholder {
  font-size: 18px; color: var(--muted);
}
.member-mgmt-spectrum {
  width: 36px; height: 48px;
  display: flex; align-items: flex-end; gap: 1px; padding: 3px;
  background: var(--border-soft); border-radius: var(--radius-sm);
  flex-shrink: 0; overflow: hidden;
}
.member-mgmt-info {
  display: flex; flex-direction: column; gap: 2px;
  justify-content: center; min-width: 0;
}
.member-mgmt-name {
  font-size: 13px; font-weight: 600; color: var(--fg);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.member-mgmt-role {
  font-size: 11px; color: var(--fg-2);
  display: flex; align-items: center; gap: 4px;
}
.member-mgmt-meta {
  font-size: 10px; color: var(--muted);
  font-family: var(--font-mono);
}

/* 操作栏 */
.member-mgmt-actionbar {
  flex-shrink: 0; padding: var(--space-3) var(--space-4);
  border-top: 1px solid var(--border);
  background: var(--surface-glass);
}
```

- [ ] **Step 2: 追加成员详情模态样式**

```css
/* ═══════════════════════════════════════════════════════════════════
   成员详情模态
   ═══════════════════════════════════════════════════════════════════ */
.member-detail-overlay {
  position: fixed; inset: 0; z-index: 70;
  background: rgba(0,0,0,0.65);
  backdrop-filter: blur(4px);
  display: flex; align-items: center; justify-content: center;
}
.member-detail-overlay.hidden { display: none; }
.member-detail-card {
  width: 340px; max-height: 85vh; overflow-y: auto;
  background: var(--surface-elevated);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  display: flex; flex-direction: column;
}
.member-detail-header {
  display: flex; align-items: center; gap: var(--space-3);
  padding: var(--space-4);
  border-bottom: 1px solid var(--border);
}
.member-detail-face {
  width: 56px; height: 56px; border-radius: var(--radius-md);
  background: var(--border-soft); overflow: hidden;
  display: grid; place-items: center; flex-shrink: 0;
}
.member-detail-face img {
  width: 100%; height: 100%; object-fit: cover;
}
.member-detail-face .face-placeholder {
  font-size: 22px; color: var(--muted);
}
.member-detail-identity {
  display: flex; flex-direction: column; gap: 2px; flex: 1;
}
.member-detail-name {
  font-size: 16px; font-weight: 600; color: var(--fg);
}
.member-detail-role {
  font-size: 12px; color: var(--fg-2);
}
.member-detail-confidence {
  font-size: 11px; color: var(--muted);
  font-family: var(--font-mono);
}
.member-detail-info {
  padding: var(--space-3) var(--space-4);
  display: flex; flex-direction: column; gap: var(--space-2);
  border-bottom: 1px solid var(--border-soft);
}
.member-detail-info-row {
  display: flex; justify-content: space-between; align-items: center;
  font-size: 12px;
}
.detail-label { color: var(--muted); }
.member-detail-info-row span:last-child {
  color: var(--fg-2); font-family: var(--font-mono);
}
.member-detail-actions {
  padding: var(--space-3) var(--space-4);
  display: flex; flex-direction: column; gap: var(--space-2);
}
.member-detail-actions .btn-sm {
  width: 100%; text-align: left; padding: 8px 12px;
  font-size: 12px;
}
```

- [ ] **Step 3: 追加历史模态样式**

```css
/* ═══════════════════════════════════════════════════════════════════
   历史指令记录模态
   ═══════════════════════════════════════════════════════════════════ */
.history-overlay {
  position: fixed; inset: 0; z-index: 80;
  background: rgba(0,0,0,0.65);
  backdrop-filter: blur(4px);
  display: flex; align-items: center; justify-content: center;
}
.history-overlay.hidden { display: none; }
.history-card {
  width: 360px; max-height: 75vh;
  background: var(--surface-elevated);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  display: flex; flex-direction: column;
  overflow: hidden;
}
.history-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--border);
}
.history-title {
  font-size: 14px; font-weight: 600; color: var(--fg);
}
.history-filter-bar {
  display: flex; gap: var(--space-2);
  padding: var(--space-2) var(--space-4);
  border-bottom: 1px solid var(--border-soft);
}
.history-filter {
  padding: 3px 10px; border-radius: var(--radius-full);
  background: var(--border-soft); border: none;
  color: var(--fg-2); font-size: 11px;
  cursor: pointer; transition: all var(--motion-fast);
}
.history-filter:hover { background: var(--surface-elevated); color: var(--fg); }
.history-filter.active {
  background: var(--accent-soft); color: var(--accent);
  font-weight: 600;
}
.history-timeline {
  flex: 1; overflow-y: auto; padding: var(--space-3) var(--space-4);
  display: flex; flex-direction: column; gap: var(--space-2);
}
.history-item {
  display: flex; gap: var(--space-2); align-items: flex-start;
  padding: var(--space-2);
  background: var(--bg); border-radius: var(--radius-sm);
  border: 1px solid var(--border-soft);
}
.history-item-type {
  font-size: 16px; flex-shrink: 0; width: 24px; text-align: center;
}
.history-item-body {
  flex: 1; display: flex; flex-direction: column; gap: 2px; min-width: 0;
}
.history-item-summary {
  font-size: 12px; color: var(--fg); line-height: 1.4;
}
.history-item-time {
  font-size: 10px; color: var(--muted);
  font-family: var(--font-mono);
}
```

- [ ] **Step 5: Commit**

```bash
git add src/electron/renderer/styles.css
git commit -m "feat(css): 新增成员管理页 + 详情模态 + 历史模态样式"
```

---

### Task 6: app.js — 视图切换 `navigateTo()` + IPC 监听

**Files:**
- Modify: `src/electron/renderer/app.js`

- [ ] **Step 1: 在 PanelManager 定义区域之后（约 line 230），新增视图路由和成员管理加载函数**

在 `function refreshMemberPanel()` 之前插入：

```js
// ═══════════════════════════════════════════════════════════
// VIEW ROUTING (main ↔ memberManagement)
// ═══════════════════════════════════════════════════════════
let currentView = 'main';

function navigateTo(view) {
  currentView = view;
  const mainStage = document.querySelector('.main-stage');
  const mmgView = $('memberManagementView');
  if (mainStage) mainStage.classList.toggle('hidden', view !== 'main');
  if (mmgView) mmgView.classList.toggle('hidden', view !== 'memberManagement');
  if (view === 'memberManagement') {
    loadMemberManagementPage();
  }
}

function loadMemberManagementPage() {
  window.frankAPI?.sendMessage?.({ type: 'member.list' });
  window.frankAPI?.sendMessage?.({ type: 'member.stats' });
}

function renderMemberManagementList(members) {
  const list = $('memberMgmtList');
  const empty = $('memberMgmtEmpty');
  if (!list) return;
  list.innerHTML = '';
  if (!members || !members.length) {
    if (empty) empty.classList.remove('hidden');
    return;
  }
  if (empty) empty.classList.add('hidden');

  members.forEach(m => {
    const badge = getRoleBadge(m.role);
    const roleName = getRoleName(m.role);

    // Face thumbnail
    const faceThumb = m.face_thumbnail
      ? `<img src="file:///${String(m.face_thumbnail).replace(/\\/g, '/').replace(/"/g, '&quot;')}" onerror="this.parentElement.innerHTML='<span class=face-placeholder>${badge}</span>'" />`
      : `<span class="face-placeholder">${badge}</span>`;

    // Voiceprint spectrum mini-bars
    let spectrumBars = '';
    if (m.voiceprint_spectrum) {
      try {
        const bins = typeof m.voiceprint_spectrum === 'string'
          ? JSON.parse(m.voiceprint_spectrum) : m.voiceprint_spectrum;
        spectrumBars = (bins || []).slice(0, 9).map(v => {
          const h = Number(v) * 48;
          if (isNaN(h) || !isFinite(h)) return '';
          return `<div class="voiceprint-mini-bar" style="height:${Math.max(2, h)}px"></div>`;
        }).filter(Boolean).join('');
      } catch (_) {}
    }

    const memberId = m.member_id || m.id || '';
    const div = document.createElement('div');
    div.className = 'member-mgmt-item';
    div.dataset.memberId = memberId;
    div.innerHTML = `
      <div class="member-mgmt-face">${faceThumb}</div>
      <div class="member-mgmt-spectrum">
        ${spectrumBars || '<span style="font-size:7px;color:var(--muted);margin:auto;">—</span>'}
      </div>
      <div class="member-mgmt-info">
        <span class="member-mgmt-name">${m.display_name || '未知'}</span>
        <span class="member-mgmt-role">${badge} ${roleName}</span>
      </div>
      <div class="member-mgmt-meta">${formatTime(m.last_active_at)}</div>`;
    div.addEventListener('click', () => openMemberDetail(memberId));
    list.appendChild(div);
  });
}

function renderMemberManagementStats(stats) {
  const countEl = $('statMembersCount');
  const visitsEl = $('statTotalVisits');
  if (countEl) countEl.textContent = stats.members_count ?? 0;
  if (visitsEl) visitsEl.textContent = stats.total_visits ?? 0;
}
```

- [ ] **Step 2: 在 `window.frankAPI.onMemberList` 回调中追加成员管理列表渲染**

找到 `window.frankAPI.onMemberList(data => {` 块（约 line 776），在 `renderMemberList(cachedMembers);` 之后追加一行：

```js
  window.frankAPI.onMemberList(data => {
    console.log('[identityPanel] onMemberList received:', data?.members?.length, 'members');
    cachedMembers = data?.members || [];
    schedulePersonListRender();
    renderMemberList(cachedMembers);
    renderMemberManagementList(cachedMembers);  // <-- 新增这行
  });
```

- [ ] **Step 3: 新增 `member.stats` `member.info` `member.history` `member.updated` IPC 监听**

在现有 IPC 绑定块中（`window.frankAPI` 条件块内，约 line 877）新增：

```js
  window.frankAPI.onMemberStats?.(data => {
    renderMemberManagementStats(data);
  });
  window.frankAPI.onMemberInfo?.(data => {
    if (data?.member) renderMemberDetailModal(data.member);
  });
  window.frankAPI.onMemberHistory?.(data => {
    if (data?.items) renderHistoryTimeline(data.items);
  });
  window.frankAPI.onMemberUpdated?.(data => {
    showToast('成员信息已更新', 'success');
    closeMemberDetail();
    loadMemberManagementPage();
    loadPersonaPanel();
  });
  window.frankAPI.onMemberDeleted?.(() => {
    showToast('成员已删除', 'success');
    closeMemberDetail();
    loadMemberManagementPage();
    loadPersonaPanel();
    refreshMemberPanel();
  });
```

- [ ] **Step 4: Commit**

```bash
git add src/electron/renderer/app.js
git commit -m "feat(app): 新增视图路由 navigateTo + 成员管理渲染 + IPC 监听"
```

---

### Task 7: app.js — 成员详情模态 + 历史模态逻辑

**Files:**
- Modify: `src/electron/renderer/app.js`（在 Task 6 新增代码之后追加）

- [ ] **Step 1: 新增成员详情模态函数**

```js
// ═══════════════════════════════════════════════════════════
// MEMBER DETAIL MODAL
// ═══════════════════════════════════════════════════════════
let _currentDetailMemberId = null;

function openMemberDetail(memberId) {
  _currentDetailMemberId = memberId;
  window.frankAPI?.sendMessage?.({ type: 'member.info', payload: { member_id: memberId } });
  window.frankAPI?.sendMessage?.({ type: 'member.history', payload: { member_id: memberId } });
  $('memberDetailOverlay')?.classList.remove('hidden');
}

function closeMemberDetail() {
  $('memberDetailOverlay')?.classList.add('hidden');
  _currentDetailMemberId = null;
}

function renderMemberDetailModal(member) {
  const badge = getRoleBadge(member.role);
  const faceThumb = member.face_thumbnail
    ? `<img src="file:///${String(member.face_thumbnail).replace(/\\/g, '/').replace(/"/g, '&quot;')}" onerror="this.parentElement.innerHTML='<span class=face-placeholder>${badge}</span>'" />`
    : `<span class="face-placeholder">${badge}</span>`;

  const faceEl = $('detailFace');
  if (faceEl) faceEl.innerHTML = faceThumb;
  const nameEl = $('detailName');
  if (nameEl) nameEl.textContent = member.display_name || '未知';
  const roleEl = $('detailRole');
  if (roleEl) roleEl.textContent = `${badge} ${getRoleName(member.role)}`;
  const confEl = $('detailConfidence');
  if (confEl) confEl.textContent = member.last_recognized_at ? `最后识别: ${formatTime(member.last_recognized_at)}` : '';

  const recogEl = $('detailRecogConfidence');
  if (recogEl) recogEl.textContent = member.recognition_confidence ? `${(member.recognition_confidence * 100).toFixed(0)}%` : '—';
  const createdEl = $('detailCreatedAt');
  if (createdEl) createdEl.textContent = member.created_at ? formatTime(member.created_at) : '—';
  const activeEl = $('detailLastActive');
  if (activeEl) activeEl.textContent = member.last_active_at ? formatTime(member.last_active_at) : '—';
  const countEl = $('detailAppearanceCount');
  if (countEl) countEl.textContent = member.appearance_count ?? '—';
}
```

- [ ] **Step 2: 新增历史记录模态函数**

```js
// ═══════════════════════════════════════════════════════════
// HISTORY MODAL
// ═══════════════════════════════════════════════════════════
let _currentHistoryItems = [];
let _currentHistoryFilter = 'all';

function openHistoryModal() {
  $('historyOverlay')?.classList.remove('hidden');
  const titleEl = $('historyTitle');
  if (titleEl && _currentDetailMemberId) {
    titleEl.textContent = `历史指令记录 — ${_currentDetailMemberId.substring(0, 8)}`;
  }
  // Re-request history to ensure data is fresh
  if (_currentDetailMemberId) {
    window.frankAPI?.sendMessage?.({ type: 'member.history', payload: { member_id: _currentDetailMemberId } });
  }
}

function closeHistoryModal() {
  $('historyOverlay')?.classList.add('hidden');
}

function renderHistoryTimeline(items) {
  _currentHistoryItems = items || [];
  _currentHistoryFilter = 'all';
  applyHistoryFilter();
}

function applyHistoryFilter() {
  const filtered = _currentHistoryFilter === 'all'
    ? _currentHistoryItems
    : _currentHistoryItems.filter(item => item.type === _currentHistoryFilter);

  const timeline = $('historyTimeline');
  const empty = $('historyEmpty');
  if (!timeline) return;

  if (!filtered.length) {
    if (empty) empty.classList.remove('hidden');
    timeline.querySelectorAll('.history-item').forEach(el => el.remove());
    return;
  }
  if (empty) empty.classList.add('hidden');

  timeline.innerHTML = filtered.map(item => {
    const icon = item.type === 'conversation' ? '💬' : '📋';
    const typeLabel = item.type === 'conversation' ? '对话' : '任务';
    return `
      <div class="history-item">
        <div class="history-item-type">${icon}</div>
        <div class="history-item-body">
          <span class="history-item-summary">${item.summary || '(无摘要)'}</span>
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <span class="history-item-time">${formatTime(item.timestamp)}</span>
            <span style="font-size:10px;color:var(--muted);">${typeLabel}</span>
          </div>
        </div>
      </div>`;
  }).join('');
}
```

- [ ] **Step 3: 新增模态 button 事件绑定 + 删除确认逻辑**

```js
// ─── Member detail modal buttons ─────────────────────────
$('btnDetailClose')?.addEventListener('click', closeMemberDetail);
$('memberDetailOverlay')?.addEventListener('click', (e) => {
  if (e.target === e.currentTarget) closeMemberDetail();
});
$('btnDetailHistory')?.addEventListener('click', openHistoryModal);
$('btnDetailEdit')?.addEventListener('click', () => {
  if (!_currentDetailMemberId) return;
  const member = cachedMembers?.find(m => (m.member_id || m.id) === _currentDetailMemberId);
  if (member) {
    openIdentifyDialog({
      mode: 'edit',
      id: _currentDetailMemberId,
      name: member.display_name || '',
      role: member.role || 'member'
    });
  }
});
$('btnDetailDelete')?.addEventListener('click', () => {
  if (!_currentDetailMemberId) return;
  if (confirm('确定要移除该成员吗？此操作不可恢复。')) {
    window.frankAPI?.sendMessage?.({ type: 'member.delete', payload: { member_id: _currentDetailMemberId } });
  }
});

// ─── History modal buttons ───────────────────────────────
$('btnHistoryClose')?.addEventListener('click', closeHistoryModal);
$('historyOverlay')?.addEventListener('click', (e) => {
  if (e.target === e.currentTarget) closeHistoryModal();
});
$('historyFilterBar')?.addEventListener('click', (e) => {
  const btn = e.target.closest('.history-filter');
  if (!btn) return;
  document.querySelectorAll('.history-filter').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  _currentHistoryFilter = btn.dataset.type;
  applyHistoryFilter();
});

// ─── Member management view buttons ──────────────────────
$('btnMemberMgmtBack')?.addEventListener('click', () => navigateTo('main'));
$('btnMemberMgmtAdd')?.addEventListener('click', openWizard);
```

- [ ] **Step 4: Commit**

```bash
git add src/electron/renderer/app.js
git commit -m "feat(app): 新增成员详情模态 + 历史模态 + 删除确认逻辑"
```

---

### Task 8: app.js — 修改入口按钮 + 移除废弃绑定

**Files:**
- Modify: `src/electron/renderer/app.js`

- [ ] **Step 1: 修改 `#btnAddMemberIdentity` 绑定**

找到 `$('btnAddMember')?.addEventListener('click', () => openWizard());` （约 line 402）和 `$('btnAddMemberIdentity')?.addEventListener('click', () => openWizard());` （约 line 403）。

将第 403 行改为：

```js
$('btnAddMemberIdentity')?.addEventListener('click', () => navigateTo('memberManagement'));
```

由于 old `membersPanel` 已从 HTML 移除，删除第 402 行 `$('btnAddMember')?.addEventListener`（该按钮已不存在）。

- [ ] **Step 2: 移除废弃的 membersPanel JS 绑定**

删除以下代码块（约 line 402，`btnAddMember` 绑定已在上一步处理）：
- `refreshMemberPanel()` 函数体（约 line 347-350）保留（identityPanel 和 member.deleted 仍需使用），但函数留空或不改。
- `renderMemberList()` 和 `renderPendingList()` 函数保留（old membersPanel 面板渲染不再需要，但保留以防后续使用，或标记为废弃）。
- `$('memberList')?.addEventListener`（约 line 383-394）— 删除（该DOM元素已不存在）。
- `$('pendingList')?.addEventListener`（约 line 396-400）— 删除（该DOM元素已不存在）。

**具体删除：**

删除 line 382-400 的整个 memberList/pendingList event delegation 块：

```js
// 删除以下内容：
// Event delegation for member lists
$('memberList')?.addEventListener('click', (e) => {
  const btn = e.target.closest('button');
  if (!btn) return;
  if (btn.dataset.action === 'delete') {
    if (confirm('确定要删除该成员吗？')) {
      window.frankAPI?.sendMessage?.({ type: 'member.delete', payload: { member_id: btn.dataset.id } });
      setTimeout(refreshMemberPanel, 500);
    }
  } else if (btn.dataset.action === 'edit') {
    window.frankAPI?.sendMessage?.({ type: 'member.register_info', payload: { member_id: btn.dataset.id } });
  }
});

$('pendingList')?.addEventListener('click', (e) => {
  const btn = e.target.closest('button');
  if (!btn) return;
  if (btn.dataset.action === 'identify') openIdentifyDialog(btn.dataset.id);
});
```

同时删除 `$('btnAddMember')?.addEventListener('click', () => openWizard());`（约 line 402）。

- [ ] **Step 3: 清理 `window.frankAPI.onMemberRegistered` 中的 `refreshMemberPanel` 调用**

找到约 line 788：
```js
window.frankAPI.onMemberRegistered(() => { showToast('成员注册成功！','success'); refreshMemberPanel(); });
```
改为：
```js
window.frankAPI.onMemberRegistered(() => { showToast('成员注册成功！','success'); loadMemberManagementPage(); loadPersonaPanel(); });
```

- [ ] **Step 4: Commit**

```bash
git add src/electron/renderer/app.js
git commit -m "refactor(app): 修改身份面板按钮跳转 + 移除废弃 membersPanel 绑定"
```

---

### Task 9: preload — 确认 IPC 通道完备

**Files:**
- Verify: `src/electron/main/preload.js`（或对应的 preload 文件）

- [ ] **Step 1: 检查 preload 中是否有新增消息类型的监听通道**

运行 grep 检查新消息类型是否已在 preload 中暴露：

```bash
grep -n "member.stats\|member.info\|member.history\|member.updated\|member.deleted" /e/docments/Frank/src/electron/main/preload.js
```

- [ ] **Step 2: 如果缺失，添加对应的 `on*` 方法**

检查当前 preload 的 `onMemberList` 模式，确认是 `on<MessageType>` 还是其他命名规则。如果 `member.stats` / `member.info` / `member.history` / `member.updated` / `member.deleted` 未被映射，则添加。预加载脚本应已支持通用 `sendMessage` + 基于消息类型的回调分发，此处验证通过即可。

**如果预加载使用通用消息回调机制（通过 `sendMessage` + `onMessage` 模式），则无需额外修改。**

- [ ] **Step 3: Commit（仅如有修改）**

```bash
git add src/electron/main/preload.js
git commit -m "fix(preload): 确保 member.stats/info/history/updated/deleted 通道就绪"
```

---

## 验证清单

全部 Tasks 完成后，执行以下验证：

1. **后端 API 检查**：
   ```bash
   cd /e/docments/Frank && .venv/Scripts/python.exe -c "
   from src.python.shared.database import init_db, get_member_stats, get_member_history, insert_command_history, get_member_by_id
   init_db()
   print('Stats:', get_member_stats())
   print('DB layer OK')
   from src.python.modules.members.member_manager import MemberManager
   print('MemberManager OK')
   "
   ```

2. **前端语法检查**：确认 `index.html` 有效、`app.js` 无语法错误、`styles.css` 无语法问题。

3. **端到端验证**：
   - 启动应用 → 打开身份识别面板 → 点击底部"成员管理"按钮 → 应切换到成员管理全窗口视图
   - 成员管理页面显示统计（成员数+访问量）和成员列表（面部缩略图+声纹频谱）
   - 点击成员条目 → 弹出详情模态（含信息、历史按钮、编辑、删除）
   - 点击"查看历史指令记录" → 弹出历史时间线模态（含类型筛选）
   - 点击"编辑信息" → 打开标识对话框（edit 模式）
   - 点击"删除成员" → confirm 对话框 → 确认后成员移除，列表刷新
   - 点击"返回"按钮 → 回到主界面
   - 原 `membersPanel` 不再出现
