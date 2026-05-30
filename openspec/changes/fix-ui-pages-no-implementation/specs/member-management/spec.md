## ADDED Requirements

### Requirement: 成员面板 WebSocket 通信

前端成员面板 SHALL 通过 `window.frankAPI.sendMessage()` 与 Python 后端通信，消息格式遵循现有 WebSocket 协议。

面板 SHALL 在以下时机发送消息：
- `member.list`：面板打开时、成员注册完成后、成员删除后 → 刷新已识别成员列表
- `member.pending`：面板打开时、访客自动发现后 → 刷新待识别访客列表
- `member.register_start`：用户点击"添加成员"按钮
- `member.register_info`：注册向导 Step 1 完成后，携带 `display_name` 和 `role`
- `member.register_cancel`：用户取消注册流程
- `member.identify`：Owner 对待识别访客执行识别操作，携带 `unidentified_id`、`display_name`、`role`
- `member.delete`：Owner 删除已识别成员，携带 `member_id`

面板 SHALL 通过 preload 中已定义的 IPC 监听器接收后端推送：
- `onMemberList` → 更新已识别成员列表 DOM
- `onMemberPending` → 更新待识别访客列表 DOM
- `onMemberRegistered` → 刷新成员列表，关闭注册向导

#### Scenario: 面板打开时拉取成员数据

- **WHEN** 用户点击"👥 成员"按钮打开成员面板
- **THEN** 面板依次发送 `member.list` 和 `member.pending` 消息，收到响应后渲染成员列表和访客列表

#### Scenario: 注册完成后刷新列表

- **WHEN** 后端发送 `member.identified` 事件
- **THEN** 面板自动重新发送 `member.list` 和 `member.pending`，更新两个列表区域

---

### Requirement: 成员面板 HTML 结构

成员面板 SHALL 在 `index.html` 中作为 `<div id="members-panel" class="panel hidden">` 元素存在。

面板内部结构 SHALL 包含：
- **面板头部**：标题"成员管理" + 关闭按钮
- **统计摘要行**：已识别成员数、待识别访客数
- **已识别成员区**：`<div id="member-list">` 容器，每行 `.member-item` 包含头像占位、显示名称、角色徽章、活跃时间、操作按钮（编辑/删除）
- **待识别访客区**：`<div id="pending-list">` 容器，每行 `.pending-item` 包含序列名、出现次数、活跃时间、[识别] 按钮
- **添加按钮**：底部"＋ 添加成员"按钮

#### Scenario: 成员面板在紧凑模式下完整显示

- **WHEN** 窗口处于紧凑模式（360px 宽），用户打开成员面板
- **THEN** 面板内容在可用宽度内正常渲染，不溢出或截断

---

### Requirement: 成员注册向导前端

注册向导 SHALL 以 Modal 叠加层（`.wizard-overlay`）形式覆盖在主界面上方，包含 4 个步骤的切换逻辑。

前端注册向导 SHALL 管理以下状态：
- 当前步骤（1-4）
- 会话 ID（从 `member.register_started` 响应获取）
- Step 1 填写的 `display_name` 和 `role`
- 注册进度（面部采集计数、声纹采集计数，通过后端事件推送更新）

Step 2（面部采集）和 Step 3（声纹采集）的进度 SHALL 由后端通过 WebSocket 事件推送更新，前端仅展示进度条和状态文案。

#### Scenario: Step 1 信息提交

- **WHEN** 用户在向导 Step 1 输入名称"小明"、选择 Child 角色、点击"下一步"
- **THEN** 前端发送 `member.register_info`，携带 `display_name: "小明"`, `role: "child"`，收到 `member.register_info_ok` 后跳转至 Step 2

#### Scenario: 取消注册

- **WHEN** 用户在向导任意步骤点击"取消"或按 Escape
- **THEN** 前端发送 `member.register_cancel`，关闭向导，丢弃进度
