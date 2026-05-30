## ADDED Requirements

### Requirement: 人物面板入口

系统 SHALL 在底部工具栏新增"人物"按钮（btn-persona），图标为 🎭，title 为"人物管理"。展开模式侧边栏 SHALL 新增"🎭 人物"导航项。点击按钮或导航项 SHALL 打开人物面板。

#### Scenario: 工具栏按钮打开人物面板

- **WHEN** 用户点击工具栏"🎭 人物"按钮
- **THEN** 人物面板显示，其他面板（设置/成员）自动隐藏

#### Scenario: 侧边栏导航打开人物面板

- **WHEN** 窗口处于展开模式，用户点击侧边栏"🎭 人物"导航项
- **THEN** 人物面板显示

---

### Requirement: 角色层级展示

人物面板 SHALL 展示 Frank 的四级角色体系，以层级卡片形式呈现。每张角色卡片 SHALL 包含：角色图标（emoji）、角色中文名称、角色英文名称、等级值、简短描述。

角色展示顺序 SHALL 为：Owner（👑 主人）→ Adult（🔵 成人）→ Child（🟢 儿童）→ Guest（⚪ 访客）。

#### Scenario: 面板展示四级角色卡片

- **WHEN** 用户打开人物面板
- **THEN** 面板以纵向排列展示四张角色卡片，按 Owner → Adult → Child → Guest 顺序，每张卡片包含图标、名称、等级值、描述

#### Scenario: Owner 卡片高亮

- **WHEN** 人物面板打开
- **THEN** Owner 角色卡片 SHALL 应用金色边框和金色脉冲动画，与其他角色卡片视觉区分

---

### Requirement: 角色权限矩阵

面板 SHALL 包含一个权限矩阵表格，以角色为列、权限项为行，使用 ✓/✗ 符号表示各角色是否拥有该权限。

权限项至少包含：成员管理、系统配置、全数据访问、常规技能、智能家居控制、日历笔记、文件操作、第三方技能、会话打断。

#### Scenario: 权限矩阵显示完整

- **WHEN** 用户打开人物面板并滚动至权限矩阵区域
- **THEN** 表格显示 9 行权限项 × 4 列角色，Owner 列全为 ✓，Guest 列仅基础问答为 ✓

#### Scenario: 权限矩阵在紧凑模式下可横向滚动

- **WHEN** 窗口处于紧凑模式（360px 宽）
- **THEN** 权限矩阵 SHALL 支持横向滚动，不挤压布局

---

### Requirement: 当前活跃身份信息

面板顶部 SHALL 显示当前已识别用户的身份信息卡片，包含：角色徽章、显示名称、角色名称、当前状态（Idle/Auth/Chat）。

若当前无已识别用户（身份未知），SHALL 显示"当前未识别用户"占位。

身份信息 SHALL 随 `identity.confirmed` 事件实时更新。

#### Scenario: 已识别用户显示身份卡片

- **WHEN** 当前已识别用户为"王小明"（Owner 角色）
- **THEN** 面板顶部显示身份卡片：👑 王小明 · 主人 · 就绪

#### Scenario: 未识别用户显示占位

- **WHEN** 当前无已识别用户
- **THEN** 面板顶部显示"当前未识别用户 — 请面对摄像头以识别身份"

---

### Requirement: 角色技能白名单展示

点击任意角色卡片 SHALL 展开该角色的技能白名单详情，列出该角色可使用的所有技能名称及简短描述。

Guest 角色的技能列表 SHALL 显示"仅基础问答（天气、时间、常识）"。

#### Scenario: 点击 Adult 卡片查看技能

- **WHEN** 用户点击 Adult 角色卡片
- **THEN** 卡片展开，显示 Adult 可用的技能列表（如：日常问答、智能家居控制、日历管理、笔记管理、信息查询等）

#### Scenario: 点击 Guest 卡片查看技能

- **WHEN** 用户点击 Guest 角色卡片
- **THEN** 卡片展开，显示"仅基础问答：天气查询、时间日期、常识问答"，不包含智能家居、日历、笔记等

---

### Requirement: 后端角色查询 API

Python 后端 SHALL 处理以下 WebSocket 消息：

- `role.list`：返回所有角色的定义信息（名称、等级值、图标、描述、可用技能列表、权限列表）
- `role.info`：接受 `role_name` 参数，返回指定角色的详细信息（含每日使用时长限制、技能白名单）

#### Scenario: role.list 返回所有角色

- **WHEN** 前端发送 `{ type: "role.list" }`
- **THEN** 后端返回 `{ type: "role.list", payload: { roles: [...] } }`，roles 数组包含 4 个角色对象

#### Scenario: role.info 返回指定角色详情

- **WHEN** 前端发送 `{ type: "role.info", role_name: "child" }`
- **THEN** 后端返回 `{ type: "role.info", payload: { name: "child", display_name: "儿童", level: 1, daily_limit_minutes: 120, skills: [...], permissions: {...} } }`
