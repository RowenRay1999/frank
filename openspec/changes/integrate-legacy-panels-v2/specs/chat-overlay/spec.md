## MODIFIED Requirements

### Requirement: Chat Overlay 布局

Chat Overlay（`#chatOverlay`）SHALL 同时拥有 `.panel-slide` 类，以复用通用面板系统的滑入/滑出机制。`openChat()` SHALL 委托给 `PanelManager.open(chatOverlay)`，`closeChat()` SHALL 委托给 `PanelManager.close(chatOverlay)`。

Chat Overlay 的内部布局（头部 + 消息区域 + 输入栏）、消息气泡样式、键盘快捷键 SHALL 保持不变。

#### Scenario: Chat Overlay 通过面板系统打开

- **WHEN** 用户点击 Orb 光球
- **THEN** `PanelManager.open(chatOverlay)` 被调用，Overlay 滑入，导航激活态不变（Chat 不绑定导航项）

#### Scenario: Chat Overlay 与设置面板互斥

- **WHEN** 设置面板已打开，用户点击 Orb 光球
- **THEN** 设置面板先关闭，Chat Overlay 随后滑入

### Requirement: 键盘快捷键

Escape 键 SHALL 优先关闭 Chat Overlay（如打开），其次关闭当前面板。空格键 SHALL 切换 Chat Overlay 的打开/关闭状态。

#### Scenario: Escape 关闭 Chat Overlay

- **WHEN** Chat Overlay 打开，用户按下 Escape 键
- **THEN** Chat Overlay 关闭

#### Scenario: Escape 关闭设置面板

- **WHEN** 设置面板打开（Chat Overlay 未打开），用户按下 Escape 键
- **THEN** 设置面板关闭，"任务看板"导航项恢复激活
