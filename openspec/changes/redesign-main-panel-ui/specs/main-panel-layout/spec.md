## ADDED Requirements

### Requirement: 手机框架式居中容器

系统 SHALL 在 Electron 窗口中渲染一个固定尺寸为 390×844px 的主面板容器（`.main-stage`），该容器居中于窗口客户区。窗口客户区背景 SHALL 为深色（`#0a0a0c`）。容器 SHALL 带有多层 box-shadow 以营造悬浮立体感：内层 2px 边框（`#1a1a1d`）、中层 4px 边框（`#0d0d0f`）、外层半透明高光线（`rgba(255,255,255,0.06)`），以及 20px 和 8px 的两级投影。

#### Scenario: 窗口显示手机框架

- **WHEN** Frank 应用启动
- **THEN** 窗口中显示一个 390×844px 的圆角容器（border-radius: 40px），居中于 430×900px 的窗口客户区，背景为深色 `#0a0a0c`

#### Scenario: 手机框架带多层阴影

- **WHEN** 主面板渲染完成
- **THEN** 容器外围共有 5 层视觉效果：内边框 `#1a1a1d`（2px）、中边框 `#0d0d0f`（4px）、外高光线 `rgba(255,255,255,0.06)`（5px）、外阴影 `rgba(0,0,0,0.7)`（20px blur 60px spread）、内阴影 `rgba(0,0,0,0.5)`（8px blur 20px spread）

### Requirement: 三区垂直布局

主面板容器（`.main-stage`）内部 SHALL 采用 flexbox 纵向布局（`flex-direction: column`），划分为三个功能区域：
1. **Zone 1 — 状态通知栏**（`.zone-status`）：固定高度，位于顶部，包含用户身份、时间、通知预览、硬件状态
2. **Zone 2 — 监控区**（`.zone-monitor`）：弹性高度（`flex: 1`），占据剩余空间，包含思考动画（上部）和任务/会话面板（下部）
3. **Zone 3 — 导航栏**（`.zone-routing`）：固定高度 48px，位于底部，包含导航项

三个区域 SHALL 通过 `border-top` / `border-bottom`（1px `var(--border-soft)`）分隔。

#### Scenario: 三区纵向排列

- **WHEN** 主面板渲染
- **THEN** 可视区域从上至下依次为：Zone 1（状态栏）→ Zone 2（监控区，占满剩余空间）→ Zone 3（导航栏，48px）

#### Scenario: Zone 1 和 Zone 3 采用毛玻璃效果

- **WHEN** 内容在 Zone 2 中滚动
- **THEN** Zone 1 和 Zone 3 保持固定位置不随内容滚动，并显示 backdrop-filter blur(20px) 的毛玻璃效果

### Requirement: 网格纹理背景

主面板容器 SHALL 包含一层 CSS `::before` 伪元素网格纹理，由 32×32px 间距的径向渐变圆点（`rgba(255,255,255,0.025)` 的 1px 圆点）组成，覆盖整个面板，`pointer-events: none`，z-index 为 0。

#### Scenario: 网格纹理覆盖面板

- **WHEN** 主面板渲染
- **THEN** 整个面板表面可见细微的 32px 间距点阵纹理，不阻挡任何交互

### Requirement: 径向渐变环境光

主面板 SHALL 在顶部中央（50% 35%）渲染一个椭圆形径向渐变光晕：中心颜色 `oklch(62% 0.16 48 / 8%)`，渐变至 55% 处完全透明，叠加于背景色之上。

#### Scenario: 面板顶部显示暖橙色光晕

- **WHEN** 主面板渲染
- **THEN** 面板顶部中央可见柔和的暖橙色环境光，从中心向外渐隐
