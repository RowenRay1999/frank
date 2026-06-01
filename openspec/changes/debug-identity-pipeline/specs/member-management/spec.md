# 成员管理 (Member Management) — Delta Spec

## MODIFIED Requirements

### Requirement: 主人标识面板 UI

成员管理面板包含已识别成员区和待识别访客区，Owner 可在面板上完成查看、编辑、删除、识别等操作。面板 MUST 在以下场景自动刷新人物列表数据：

- 面板首次打开时加载全部数据
- 收到 `identity.confirmed` 事件时（若面板已打开）
- 收到 `identity.unknown` 事件且包含 `auto_discovered` 信息时（若面板已打开）

面板刷新通过发送 `member.list` 和 `member.pending` 请求并重新渲染实现。

#### Scenario: 面板加载显示正确的成员和访客信息

1. 前置条件：Owner 已登录，数据库中已识别成员 3 人（王小明-owner、张丽-admin、小波-member），待识别访客 2 人（访客-003、访客-007）。
2. Owner 点击主界面的"成员管理"入口。
3. 面板加载并呈现两栏布局：
   - 左栏/上栏"已识别成员"列表，按最近活跃时间倒序排列：王小明（Owner 标签，头像，今日活跃）、张丽（Admin 标签，头像，昨天活跃）、小波（Member 标签，头像，3 天前活跃）。每行右侧有 [编辑] 和 [删除] 按钮。
   - 右栏/下栏"待识别访客"列表，按最近出现时间倒序排列：访客-007（出现 8 次，最后出现 2 小时前）、访客-003（出现 12 次，最后出现昨天）。每行右侧有 [识别] 按钮。
4. 后置条件：面板正确渲染所有成员信息。

#### Scenario: 身份确认后面板自动刷新已识别成员列表

- **WHEN** 身份面板已打开，`identity.confirmed` 事件到达（确认了成员"王小明"）
- **THEN** 面板发送 `member.list` 请求，返回的成员列表包含更新的 `last_active_at`、`recognition_confidence` 等字段，面板重新渲染已识别成员区

#### Scenario: 新未标识访客自动发现后面板刷新

- **WHEN** 身份面板已打开，`identity.unknown` 事件到达且 `auto_discovered.is_new === true`（新访客"访客-005"被自动发现）
- **THEN** 面板发送 `member.pending` 请求，返回的待识别列表包含新访客"访客-005"，面板重新渲染待识别区

#### Scenario: 面板关闭时收到事件不触发请求

- **WHEN** 身份面板未打开，`identity.confirmed` 或 `identity.unknown` 事件到达
- **THEN** 前端不发送 `member.list` 或 `member.pending` 请求（避免无谓通信）

#### Scenario: 面板编辑已识别成员信息

1. 前置条件：面板已打开，王小明（owner）成员行可见。
2. Owner 点击王小明行的 [编辑] 按钮。
3. 弹窗显示编辑表单：名称（王小明）、角色（owner 灰化不可修改，系统限制仅 1 个 owner）。可选操作："重新采集人脸"、"重新采集声纹"。
4. Owner 将名称改为"王大明"，点击保存。
5. 系统更新 members 表 display_name 为"王大明"。面板刷新显示新的名称。
6. 后置条件：members 表对应记录的 display_name 已更新。

#### Scenario: 未标识人物 display_name 正确显示

- **WHEN** 后端 `unidentified` 表返回记录包含 `display_name: "访客-001"`
- **THEN** 前端身份面板人物列表使用 `p.display_name` 显示"访客-001"，而非使用不存在的 `p.serial_name` 字段
