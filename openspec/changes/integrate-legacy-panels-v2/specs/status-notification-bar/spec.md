## MODIFIED Requirements

### Requirement: 通知预览

上行右侧（时钟旁）SHALL 显示通知预览按钮（`.notif-preview`）……（视觉样式不变）。

点击通知预览 SHALL 打开通知面板（`PanelManager.open(notifPanel)`），而非导航至 `notifications.html`。

#### Scenario: 点击通知预览打开面板

- **WHEN** 用户点击通知预览按钮
- **THEN** 通知面板从右侧滑入，"通知中心"导航项变为激活态
