## MODIFIED Requirements

### Requirement: 导航项

导航栏 SHALL 包含 5 个导航项，每个 SHALL 为 `<a>` 标签，`href="#"`，通过 `onclick` 事件（`event.preventDefault()` + 面板触发）来打开对应面板，而非页面跳转。

导航项与面板的映射关系 SHALL 为：
1. **身份识别** → `#identityPanel`（人物角色面板）
2. **任务看板** → `#taskDetailPanel`（任务详情面板），默认激活态
3. **通知中心** → `#notifPanel`（通知面板）
4. **分隔线**（无变化）
5. **设置** → `#settingsPanel`（设置面板）

导航项的视觉样式（图标、标签、间距、圆角）SHALL 不变。分隔线 SHALL 不变。

#### Scenario: 点击导航项打开面板

- **WHEN** 用户点击"设置"导航项
- **THEN** 设置面板从右侧滑入，导航项变为激活态（橙色），其他导航项恢复默认

#### Scenario: 关闭面板时导航项恢复

- **WHEN** 用户关闭设置面板（点击 ✕ 或按 Escape）
- **THEN** "设置"导航项恢复默认灰色，"任务看板"导航项重新激活

### Requirement: 导航项激活态联动

激活导航项 SHALL 跟随当前打开的面板变化。当面板通过 `PanelManager.open()` 打开时，对应的导航项 SHALL 添加 `.active` 类。当面板关闭时，`.active` 类 SHALL 移除。关闭所有面板时，默认激活项恢复为"任务看板"。

#### Scenario: 面板切换联动导航激活态

- **WHEN** 任务详情面板打开后，用户点击"身份识别"导航项
- **THEN** "任务看板"恢复默认色，"身份识别"变为橙色激活态
