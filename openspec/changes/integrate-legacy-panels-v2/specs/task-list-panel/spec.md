## MODIFIED Requirements

### Requirement: 任务列表区域布局

（不变——保留原需求）
Zone 2 下部（`.monitor-bottom`）SHALL 包含任务列表区域……（HTML 结构和视觉样式不变）

"查看全部"链接 SHALL 触发任务详情面板（`PanelManager.open(taskDetailPanel)`），而非导航至 `tasks.html`。

#### Scenario: 点击查看全部打开任务详情面板

- **WHEN** 用户点击任务列表头部的"查看全部"链接
- **THEN** 任务详情面板从右侧滑入，"任务看板"导航项保持激活态
