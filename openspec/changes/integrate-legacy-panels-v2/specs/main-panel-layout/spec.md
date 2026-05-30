## MODIFIED Requirements

### Requirement: 手机框架式居中容器

~~系统 SHALL 在 Electron 窗口中渲染一个固定尺寸为 390×844px 的主面板容器（`.main-stage`），该容器居中于窗口客户区。窗口客户区背景 SHALL 为深色（`#0a0a0c`）。容器 SHALL 带有多层 box-shadow 以营造悬浮立体感。~~

系统 SHALL 在 Electron 窗口中渲染一个填满窗口客户区（`width: 100vw; height: 100vh`）的主面板容器（`.main-stage`），无圆角（`border-radius: 0`），无 phone-frame 包裹层。窗口客户区背景 SHALL 为深色（`#0a0a0c`）。

#### Scenario: 主面板填满窗口

- **WHEN** Frank 应用启动，窗口尺寸为 800×600
- **THEN** `.main-stage` 容器占据 800×600 像素，无圆角，无外阴影

#### Scenario: 窗口缩放时主面板跟随

- **WHEN** 用户拖拽窗口边缘调整尺寸
- **THEN** `.main-stage` 自动扩展/收缩至新的窗口客户区尺寸

### Requirement: 三区垂直布局

主面板容器（`.main-stage`）内部 SHALL 保持 flexbox 纵向布局（`flex-direction: column`），三个区域的功能和顺序不变：

1. **Zone 1 — 状态通知栏**（`.zone-status`）：内容驱动高度，`flex-shrink: 0`
2. **Zone 2 — 监控区**（`.zone-monitor`）：`flex: 1`，占据所有剩余空间
3. **Zone 3 — 导航栏**（`.zone-routing`）：固定高度 48px，`flex-shrink: 0`

#### Scenario: 三区比例自适应

- **WHEN** 窗口高度从 600 变为 900
- **THEN** Zone 1 和 Zone 3 高度不变（约 80px + 48px），Zone 2 高度增加约 300px

### Requirement: 网格纹理背景

（不变——保留原需求）
主面板容器 SHALL 包含一层 CSS `::before` 伪元素网格纹理……`pointer-events: none`，z-index 为 0。

### Requirement: 径向渐变环境光

（不变——保留原需求）
主面板 SHALL 在顶部中央渲染一个椭圆形径向渐变光晕……
