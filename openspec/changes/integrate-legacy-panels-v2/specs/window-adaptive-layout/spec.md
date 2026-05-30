## ADDED Requirements

### Requirement: 全窗口弹性布局

系统 SHALL 移除 `.phone-frame` 包裹层，`.main-stage` 直接作为窗口客户区的根容器，尺寸 SHALL 为 `width: 100vw; height: 100vh`，无圆角（`border-radius: 0`）。body SHALL 使用 `display: block`（非 flex 居中），背景色为 `var(--bg)`。

#### Scenario: 主面板填满窗口

- **WHEN** Frank 应用启动，窗口尺寸为 800×600
- **THEN** `.main-stage` 容器精确占据 800×600 像素，无圆角，无外阴影

#### Scenario: 窗口缩放时主面板跟随

- **WHEN** 用户拖拽窗口边缘将尺寸从 800×600 调整为 1000×700
- **THEN** `.main-stage` 自动扩展至 1000×700，三区高度按 flex 比例重新分配

### Requirement: 三区弹性高度自适应

Zone 1（`.zone-status`）和 Zone 3（`.zone-routing`）SHALL 保持内容驱动高度（`flex-shrink: 0`）。Zone 2（`.zone-monitor`）SHALL 占据剩余全部空间（`flex: 1`）。

Zone 2 内部 `.monitor-thinking` 与 `.monitor-bottom` SHALL 保持现有的 flex 比例分配逻辑（thinking: `flex: 0 0 42%`，bottom: `flex: 1`），使得 Orb 区域随窗口高度等比例缩放。

#### Scenario: 高窗口下 Orb 区域增大

- **WHEN** 窗口高度从 600 增至 900
- **THEN** `.monitor-thinking` 高度从约 252px 增至约 378px（42% 比例），Orb 保持居中

#### Scenario: 低窗口下任务列表仍可见

- **WHEN** 窗口高度减小至 400（最小高度）
- **THEN** Zone 1 和 Zone 3 保持固定高度，`.monitor-bottom` 至少仍有足够空间显示 section-header

### Requirement: 窗口拖拽区域

Zone 1 状态栏（`.zone-status`）SHALL 设为 `-webkit-app-region: drag` 以支持窗口拖动。Zone 1 内部的交互元素（按钮、通知预览）SHALL 设为 `-webkit-app-region: no-drag` 以保持可点击。外置窗口控制条 SHALL 保留在原地（`position: fixed; top: 16px; right: 16px`）。

#### Scenario: 拖拽 Zone 1 移动窗口

- **WHEN** 用户在 Zone 1 状态栏区域按住鼠标并拖拽
- **THEN** 整个 Electron 窗口跟随鼠标移动

#### Scenario: Zone 1 内按钮仍可点击

- **WHEN** 用户点击 Zone 1 内的通知预览按钮
- **THEN** 通知面板正常打开，不触发窗口拖拽

### Requirement: 环境光与网格纹理保留

`.main-stage` SHALL 保留径向渐变环境光（`radial-gradient(ellipse at 50% 35%, oklch(62% 0.16 48 / 8%), transparent 55%)`）和 `::before` 伪元素网格纹理（32px 间距圆点），不因移除 phone-frame 而丢失。

#### Scenario: 全窗口下仍可见环境光

- **WHEN** 应用启动
- **THEN** 面板顶部中央可见柔和暖橙色光晕，全表面可见细微点阵纹理
