# 成员管理独立页面设计规范

> 日期：2026-06-01 | 状态：已确认 | 分支：develop-base-v0

## 1. 概述

将身份识别面板的"添加成员"按钮改为成员管理页面入口，新建一个独立的成员管理视图，包含已标识成员列表、操作栏和信息统计三个区域。

## 2. 变更目标

- 身份识别面板底部按钮从"打开注册向导"改为"跳转成员管理页面"
- 新建全窗口成员管理视图，替代现有 `membersPanel` 滑入面板
- 成员列表提供面部分缩略图、声纹频谱可视化、点击展开详情模态
- 详情模态包含成员信息、历史指令记录查看入口（按角色区分保留天数）、编辑与删除操作

## 3. 架构

### 3.1 导航方案：全窗口视图切换

在现有 `index.html` 中新增 `#memberManagementView` 节点，与 `.main-stage` 平级。通过 JS 视图路由 `navigateTo('main' | 'memberManagement')` 控制显隐。保持现有 WebSocket 连接和 IPC 通道复用。

```
index.html
├── .main-stage              ← 主页（隐藏/显示）
└── #memberManagementView    ← 成员管理（隐藏/显示）
```

### 3.2 组件树

```
MemberManagementView
├── TopBar
│   ├── BackButton                 → navigateTo('main')
│   ├── PageTitle                  "成员管理"
│   └── StatsBar
│       ├── StatCard               "成员总数"   (members_count)
│       └── StatCard               "总访问量"   (sum appearance_count)
├── MemberList (可滚动)
│   └── MemberItem[]
│       ├── FaceThumbnail          <img> 本地文件路径，加载失败显示角色图标兜底
│       ├── VoiceprintBars         频谱 mini-bar 可视化 (同 identityPanel)
│       ├── DisplayName
│       ├── RoleBadge              角色图标 + 角色名
│       └── LastActiveTime         最近活跃时间
└── ActionBar
    └── AddButton                  "＋ 新增成员" → 复用现有 openWizard()
```

### 3.3 详情模态

```
MemberDetailModal (绝对定位覆盖层 + 半透明背景遮罩)
├── Header
│   ├── FaceThumbnail (大尺寸)
│   ├── DisplayName + RoleBadge
│   └── LastRecognizedAt 置信度
├── InfoSection
│   ├── 识别置信度: XX%
│   ├── 注册时间
│   ├── 最后活跃
│   └── 访问次数
├── HistoryEntry                   按钮 "查看历史指令记录"
│   → 打开 HistoryModal（对话 + 任务时间线，按角色区分保留天数）
├── EditButton                     按钮 "编辑信息"
│   → 复用现有 identifyDialog（edit 模式）
└── DeleteButton                   按钮 "删除成员"
    → 弹出确认对话框 confirm() → member.delete → 刷新列表
```

### 3.4 历史记录模态

```
HistoryModal
├── 标题 "历史指令记录 — {display_name}"
├── FilterBar（可选：全部 / 对话 / 任务）
└── TimelineList
    └── TimelineItem[]
        ├── 时间戳
        ├── 类型标签（对话/任务）
        └── 摘要内容
```

## 4. 数据模型

### 4.1 成员列表项字段

| 字段 | 类型 | 来源 | 说明 |
|---|---|---|---|
| id / member_id | string | DB | 唯一标识 |
| display_name | string | DB | 显示名称 |
| role | string | DB | owner/admin/member/guest |
| face_thumbnail | string(路径) | DB | 面部缩略图本地路径 |
| voiceprint_spectrum | number[] | DB | 声纹频谱 48-bin 数组 |
| last_active_at | string(ISO) | DB | 最后活跃时间 |
| last_recognized_at | string(ISO) | DB | 最后识别时间 |
| recognition_confidence | number | DB | 识别置信度 0-1 |
| appearance_count | number | DB | 总出现次数 |
| created_at | string(ISO) | DB | 注册时间 |

### 4.2 统计栏字段

| 字段 | 来源 |
|---|---|
| members_count | `SELECT COUNT(*) FROM members WHERE labeled=1` |
| total_visits | `SELECT SUM(appearance_count) FROM members WHERE labeled=1` |

### 4.3 历史记录字段

| 字段 | 说明 |
|---|---|
| type | `conversation` 或 `task` |
| timestamp | 发生时间 |
| summary | 摘要（对话前 100 字 / 任务标题） |
| detail | 完整内容（对话全文 / 任务参数） |

### 4.4 历史记录保留策略

| 角色 | 保留期限 |
|---|---|
| owner, admin | 无限期 |
| member, guest | 120 天 |
| unregistered | 无历史记录 |

## 5. API 变更

### 5.1 补全已有消息路由（Bugfix）

`member.update` 在前端已调用但 `main.py` 缺少对应路由，需补全：

| 类型 | 请求 | 响应 |
|---|---|---|
| `member.update` | `{type:"member.update", payload:{member_id, display_name, role}}` | `{type:"member.updated", member:{...}}` |

`member_manager.update_member_info()` 和 `database.update_member()` 已实现，仅缺 WebSocket 路由。

### 5.2 新增 WebSocket 消息

| 类型 | 请求 | 响应 |
|---|---|---|
| `member.stats` | `{type:"member.stats"}` | `{type:"member.stats", members_count:N, total_visits:N}` |
| `member.info` | `{type:"member.info", payload:{member_id}}` | `{type:"member.info", member:{...全部字段...}}` |
| `member.history` | `{type:"member.history", payload:{member_id}}` | `{type:"member.history", items:[{type, timestamp, summary, detail}]}` |

### 5.3 保留期限逻辑

- 后端 `member.history` 根据请求成员的角色决定返回范围
- owner/admin → 返回全部历史
- member/guest → 仅返回 120 天内的记录
- unregistered → 返回空数组

## 6. 前端变更

### 6.1 导航系统

```js
// 新增加
let currentView = 'main';  // 'main' | 'memberManagement'

function navigateTo(view) {
  currentView = view;
  $('mainStage').classList.toggle('hidden', view !== 'main');
  $('memberManagementView').classList.toggle('hidden', view !== 'memberManagement');
  if (view === 'memberManagement') {
    loadMemberManagementPage();
  }
}
```

### 6.2 入口点修改

- `identityPanel` 底部 `#btnAddMemberIdentity` 点击 → `navigateTo('memberManagement')`
- `membersPanel` 整体移除（HTML + JS 绑定 + CSS 样式）
- 导航栏如有 `membersPanel` 入口一并移除

### 6.3 列表渲染

- 复用现有 `getRoleBadge()` / `getRoleName()` / `formatTime()` 工具函数
- 面部缩略图渲染：复用 identityPanel 的 `<img>` + onerror 兜底模式
- 声纹频谱：复用 identityPanel 的 `voiceprint-mini-bar` 样式

### 6.4 模态管理

- `openMemberDetail(memberId)` → 发送 `member.info` + `member.history` → 渲染模态
- `closeMemberDetail()` → 隐藏模态
- `openHistoryModal(memberId)` → 渲染历史时间线
- `closeHistoryModal()` → 返回详情模态
- 删除确认：`confirm("确定要移除该成员吗？此操作不可恢复。")` → `member.delete`

## 7. 后端变更

### 7.1 `main.py` 新增路由

```python
case 'member.stats':
    stats = member_manager.get_stats()
    await send_message(websocket, 'member.stats', stats, msg_id)

case 'member.info':
    info = member_manager.get_member_info(payload['member_id'])
    await send_message(websocket, 'member.info', {'member': info}, msg_id)

case 'member.history':
    member = member_manager.get_member_info(payload['member_id'])
    role = member.get('role', 'guest')
    days = None if role in ('owner', 'admin') else 120
    history = member_manager.get_member_history(payload['member_id'], days)
    await send_message(websocket, 'member.history', history, msg_id)
```

### 7.2 `member_manager.py` 新增方法

- `get_stats() → dict` — 聚合计数
- `get_member_info(member_id) → dict` — 单成员完整信息
- `get_member_history(member_id, max_age_days) → dict` — 查询对话+任务记录

### 7.3 `database.py` 新增表与查询

**新增 `command_history` 表：**

```sql
CREATE TABLE IF NOT EXISTS command_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id TEXT NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('conversation', 'task')),
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    summary TEXT NOT NULL DEFAULT '',
    detail TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_cmd_history_member ON command_history(member_id, timestamp);
```

**新增查询函数：**

- `get_member_by_id(member_id)` — 按 ID 查询单成员（排除 BLOB 列，使用 `_row_to_json_dict`）
- `get_member_history(member_id, max_age_days)` — 查询 `command_history` 表；若 `max_age_days` 为 None 则返回全部
- `insert_command_history(member_id, type, summary, detail)` — 写入指令记录
- `get_member_stats()` — 返回 `{members_count, total_visits}`

## 8. 样式设计

### 8.1 布局原则

- 延续现有设计令牌体系（oklch 色彩、间距刻度、玻璃态）
- 成员管理页采用全窗口 flex 纵向布局：TopBar(固定) + MemberList(flex-grow 可滚动) + ActionBar(固定)
- 列表条目高度紧凑（≈64px），包含缩略图+频谱+信息+时间
- 模态采用居中卡片 + `backdrop-filter: blur()` 遮罩

### 8.2 关键 CSS 类命名

```css
.member-mgmt-view           /* 全窗口容器 */
.member-mgmt-topbar         /* 顶部栏 flex row */
.member-mgmt-stat           /* 统计卡片 */
.member-mgmt-list           /* 成员列表滚动区 */
.member-mgmt-item           /* 单条成员 */
.member-mgmt-face           /* 面部缩略图 */
.member-mgmt-spectrum       /* 声纹频谱 */
.member-detail-overlay      /* 详情模态遮罩 */
.member-detail-card         /* 详情模态卡片 */
.history-overlay            /* 历史模态 */
.history-timeline           /* 历史时间线 */
```

## 9. 文件变更清单

| 文件 | 操作 | 说明 |
|---|---|---|
| `src/electron/renderer/index.html` | 修改 | 新增 `#memberManagementView`、`#memberDetailModal`、`#historyModal`；移除 `#membersPanel` 及其引用 |
| `src/electron/renderer/app.js` | 修改 | 新增视图切换、成员页面渲染、模态管理函数；移除 membersPanel 绑定；修改 `#btnAddMemberIdentity` 行为 |
| `src/electron/renderer/styles.css` | 修改 | 新增成员管理页/模态/时间线样式；移除废弃的 membersPanel 专属样式 |
| `src/python/server/main.py` | 修改 | 新增 3 条 WebSocket 消息路由 |
| `src/python/modules/members/member_manager.py` | 修改 | 新增 `get_stats()` / `get_member_info()` / `get_member_history()` |
| `src/python/shared/database.py` | 修改 | 新增 `get_member_by_id()` / `get_member_history()` 查询 |

## 10. 已解决的实现前置问题

### 10.1 历史记录存储

经代码库验证，数据库当前**没有** `conversations` 或 `tasks` 持久化表（前端 taskHistory 仅在内存中）。本次变更将新建 `command_history` 表（见 7.3 节），统一存储对话和任务指令记录。后续其他模块（对话引擎、任务系统）在产生记录时也写入此表。

### 10.2 总访问量统计

`total_visits` 使用 `SUM(appearance_count)` 聚合，不需要额外的 `visit_log` 表。该字段已存在于 members 表且随每次识别递增。

### 10.3 `member.update` 路由缺失

前端 `app.js:578` 已调用 `member.update`，但 `main.py` 缺少对应的 WebSocket 路由。本次变更将补全该路由（见 5.1 节），连通已有 `member_manager.update_member_info()` 实现。
