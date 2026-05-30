## ADDED Requirements

### Requirement: 底部导航栏布局

Zone 3（`.zone-routing`）SHALL 为固定在主面板底部的水平导航栏，高度 48px（`min-height: 48px`），flex 水平居中布局（`justify-content: center`），gap `var(--space-1)`（4px），内边距 `var(--space-2) var(--space-4)`。

导航栏 SHALL 应用毛玻璃效果（`var(--surface-glass)` + `backdrop-filter: blur(20px)`），顶部 `1px solid var(--border-soft)` 分隔线。

#### Scenario: 导航栏固定在底部

- **WHEN** 主面板渲染
- **THEN** 底部显示 48px 高的导航栏，毛玻璃半透明背景，内有 5 个导航项

### Requirement: 导航项

导航栏 SHALL 包含 5 个导航项：
1. **身份识别**（链接至 `identity.html`）：主 icon — 用户轮廓 + 添加标记 SVG
2. **任务看板**（链接至 `tasks.html`）：主 icon — 日历/表格 SVG，默认激活态
3. **通知中心**（链接至 `notifications.html`）：主 icon — 铃铛 SVG
4. **分隔线**（`.route-divider`）：1px 宽 24px 高的竖线，`var(--border)` 色
5. **设置**（链接至 `settings.html`）：主 icon — 齿轮 SVG

每个导航项（`.route-item`）SHALL 为纵向 flex 布局（图标在上，标签在下），gap 3px，内边距 `var(--space-1) var(--space-2)`，圆角 `var(--radius-md)`，最小宽度 64px，`cursor: pointer`。

#### Scenario: 导航项渲染

- **WHEN** 主面板渲染
- **THEN** 导航栏依次显示：身份识别 → 任务看板（激活） → 通知中心 → | 分隔线 → 设置

### Requirement: 导航项交互状态

导航项 SHALL 支持以下交互状态：
- **默认**：文字色 `var(--fg-2)`，图标 opacity 0.65
- **悬停**：文字色 `var(--fg)`，背景 `var(--border-soft)`，图标 opacity 1
- **激活**（`.active`）：文字色 `var(--accent)`（橙色），图标 opacity 1

激活态与非激活态的过渡 SHALL 使用 `var(--motion-fast)`（150ms）和 `var(--ease-standard)` 缓动。

#### Scenario: 悬停非激活导航项

- **WHEN** 用户鼠标悬停在"设置"导航项上
- **THEN** 文字颜色从灰色变为白色，背景出现半透明，图标完全不透明

#### Scenario: 点击切换激活导航项

- **WHEN** 用户点击"身份识别"导航项
- **THEN** "身份识别"变为橙色，"任务看板"恢复灰色，浏览器导航至 identity.html

### Requirement: 导航项图标

每个导航项的图标 SHALL 为内联 SVG（20×20px viewBox "0 0 24 24"），描边宽度 1.6px，颜色继承当前文字色。导航项底部的文字标签 SHALL 为 10px，weight 500，letter-spacing 0.02em。

#### Scenario: 激活导航项图标高亮

- **WHEN** "任务看板"为激活导航项
- **THEN** 其 SVG 图标为橙色（`var(--accent)`），opacity 1

### Requirement: 导航项链接行为

每个导航项 SHALL 为 `<a>` 标签，`href` 指向对应的功能页面。分隔线 SHALL 为 `<div>`，不可点击。所有导航项的 `text-decoration` SHALL 为 `none`。

#### Scenario: 点击导航项跳转页面

- **WHEN** 用户点击"设置"导航项
- **THEN** 浏览器/Electron 窗口导航至 settings.html
