# ui-shell — 桌面 UI 外壳

## ADDED Requirements

### Requirement: 窗口管理

系统 SHALL 在 Electron 渲染进程中创建一个无边框浮动窗口，默认以紧凑模式（compact mode）启动，尺寸为 360×500px。窗口 SHALL 支持自定义标题栏实现拖动。系统 MUST 提供"总在最前"（always-on-top）切换按钮。窗口 MUST 支持通过拖拽边缘进行缩放，最小尺寸 300×400px，最大尺寸 1200×900px。窗口位置 SHALL 在会话间持久化（使用 electron-store 或配置文件存储）。系统 MUST 提供一个展开按钮，点击后切换至完整模式（full mode，800×600px），并在展开模式下显示侧边栏区域。

#### Scenario: 默认启动尺寸为紧凑模式
- **WHEN** 用户首次启动 Frank
- **THEN** 窗口以紧凑模式呈现，尺寸为 360×500px，显示自定义标题栏和主内容区域

#### Scenario: 拖拽边缘调整窗口尺寸
- **WHEN** 用户拖拽窗口任意边缘或角落
- **THEN** 窗口跟随鼠标缩放，且尺寸被限制在最小 300×400px 至最大 1200×900px 之间

#### Scenario: 展开按钮切换全模式
- **WHEN** 用户点击标题栏上的展开按钮
- **THEN** 窗口切换至全模式（800×600px），侧边栏区域可见

#### Scenario: 再次点击展开按钮恢复紧凑模式
- **WHEN** 用户在全模式下再次点击展开按钮
- **THEN** 窗口恢复至紧凑模式（360×500px），侧边栏隐藏

#### Scenario: 窗口位置被持久化
- **WHEN** 用户调整窗口位置后关闭并重新启动 Frank
- **THEN** 窗口恢复至上次关闭时的屏幕位置

### Requirement: 自定义标题栏

系统 MUST 使用自定义标题栏替代操作系统原生标题栏。标题栏从左至右依次包含：状态指示点（圆点）、当前状态标签（显示"Frank - 待机中" / "检测中..." / "就绪" / "对话中"）、窗口控制按钮组（最小化、展开/最大化、关闭）。标题栏 SHALL 支持鼠标拖拽移动整个窗口。

#### Scenario: 标题栏显示正确的状态文本
- **WHEN** 系统状态从 Idle 变更为 Chat
- **THEN** 标题栏状态标签更新为"Frank - 对话中"

#### Scenario: 拖拽标题栏移动窗口
- **WHEN** 用户在标题栏区域按下鼠标左键并拖动
- **THEN** 窗口跟随鼠标移动，释放鼠标后窗口停留在新位置

#### Scenario: 点击关闭按钮退出
- **WHEN** 用户点击标题栏右侧的关闭按钮
- **THEN** 窗口隐藏至系统托盘（而非退出应用）

#### Scenario: 点击最小化按钮
- **WHEN** 用户点击标题栏的最小化按钮
- **THEN** 窗口最小化至系统托盘

### Requirement: 状态指示器

系统 MUST 在标题栏左侧显示一个彩色圆点作为状态指示器，反映底层状态机的当前状态。各状态对应的颜色定义如下：
- ⚪ 灰色（Gray）：Idle — 待机中
- 🔵 蓝色脉冲（Blue pulse）：Aware — 检测到人...
- 🟢 绿色（Green）：Auth — 就绪
- 🟣 紫色脉冲（Purple pulse）：Chat — 对话中
- 🟡 黄色（Yellow）：Degraded — 降级模式（摄像头或麦克风不可用）

脉冲动画 MUST 通过 CSS animation 实现，包含 scale 和 opacity 的周期变化。

#### Scenario: 待机状态显示灰色圆点
- **WHEN** 状态机处于 Idle 状态
- **THEN** 指示点显示为灰色（#9E9E9E），无动画

#### Scenario: 感知状态显示蓝色脉冲动画
- **WHEN** 状态机进入 Aware 状态
- **THEN** 指示点变为蓝色（#2196F3），并启动脉冲 CSS 动画（scale 从 1 到 1.3，opacity 从 1 到 0.6，周期 1.5s）

#### Scenario: 降级模式显示黄色
- **WHEN** 摄像头或麦克风不可用导致状态机进入 Degraded 状态
- **THEN** 指示点变为黄色（#FFC107），无动画

### Requirement: 聊天面板占位

系统 MUST 在主内容区域展示聊天面板占位界面。当无对话时，面板 SHALL 显示欢迎语"下午好，需要我做些什么？"（该文本可配置）。面板中央 SHALL 提供一个可滚动的消息列表区域（Phase 1 为空占位，Phase 3 将填充真实消息）。面板底部 SHALL 显示一个禁用的输入区域，背景灰色，占位文本为"语音监听中..."（Phase 1 不支持文本输入）。当状态变更为 Chat 时，输入区域 SHALL 将占位文本更新为"正在听..."。

#### Scenario: 首次启动显示欢迎语
- **WHEN** 应用首次启动且无历史对话
- **THEN** 消息列表区域中央显示"下午好，需要我做些什么？"欢迎语

#### Scenario: 禁用输入框显示监听占位
- **WHEN** 状态为 Idle 或 Aware 或 Auth
- **THEN** 底部输入框呈灰色禁用状态，占位文本为"语音监听中..."

#### Scenario: 对话状态下输入框提示变化
- **WHEN** 系统状态变更为 Chat
- **THEN** 底部输入框占位文本更新为"正在听..."

### Requirement: 系统托盘

系统 MUST 在 Windows 系统托盘中始终显示应用图标。托盘右键菜单 SHALL 包含以下菜单项：显示/隐藏窗口（Show/Hide）、状态子菜单（显示当前状态）、设置（Phase 1 置灰禁用）、退出（Quit）。双击托盘图标 SHALL 切换窗口的显示/隐藏状态。点击窗口关闭按钮 SHALL 将应用最小化至托盘而非任务栏。

#### Scenario: 双击托盘图标切换窗口
- **WHEN** 窗口处于隐藏状态且用户双击托盘图标
- **THEN** 窗口显示并置于最前

#### Scenario: 托盘菜单显示当前状态
- **WHEN** 用户右键点击托盘图标并悬停在"Status"子菜单
- **THEN** 子菜单中显示当前状态文本（如"待机中"）

#### Scenario: 设置菜单项置灰
- **WHEN** Phase 1 中用户点击托盘菜单的"Settings"
- **THEN** 菜单项呈灰色禁用状态，无任何响应

#### Scenario: 关闭窗口最小化到托盘
- **WHEN** 用户点击窗口的关闭按钮
- **THEN** 窗口隐藏，应用继续在系统托盘运行

### Requirement: 设置面板占位

系统 MUST 提供一个设置面板的访问入口，可从系统托盘菜单或展开模式侧边栏进入。设置面板内容区域 SHALL 显示占位信息"设置功能将在后续版本中开放"。Phase 1 仅包含设置访问入口，不包含功能性设置界面。

#### Scenario: 从侧边栏打开设置面板
- **WHEN** 用户处于全模式并在侧边栏点击"设置"入口
- **THEN** 主内容区域显示占位文本"设置功能将在后续版本中开放"

#### Scenario: 从托盘菜单打开设置面板
- **WHEN** 用户右键托盘图标并点击"Settings"
- **THEN** 窗口显示（如隐藏），主内容区域显示占位文本"设置功能将在后续版本中开放"

### Requirement: 开机自启

系统 SHALL 支持配置开机自启动。在 Windows 平台上通过注册表 Run 键实现。该选项通过配置文件 `config/frank.yaml` 中的 `auto_start: true/false` 控制。默认值为 `true`（启用）。应用启动时 SHALL 读取该配置并调用 Electron 的 `app.setLoginItemSettings` 设置开机自启。

#### Scenario: 默认启用开机自启
- **WHEN** 用户安装 Frank 后首次启动
- **THEN** 应用读取 `config/frank.yaml` 中 `auto_start: true`，通过 `app.setLoginItemSettings` 注册 Windows 开机自启

#### Scenario: 配置关闭开机自启
- **WHEN** 用户在 `config/frank.yaml` 中将 `auto_start` 设置为 `false` 后重启应用
- **THEN** 应用移除注册表中的自启项，下次开机不再自动启动

### Requirement: IPC 集成

系统 MUST 实现主进程与渲染进程之间的 IPC 通信。渲染器通过 `contextBridge` 暴露的 API 监听主进程转发的状态变更事件。主进程 SHALL 接收来自 Python 后端的状态事件并转发至渲染进程。渲染器收到状态变更后 SHALL 响应式地更新 UI：状态指示点颜色、标题栏文本和面板内容。禁止使用轮询机制。

#### Scenario: 状态变更通过 IPC 传递到渲染器
- **WHEN** Python 后端发出状态变更事件（例如从 Idle 变为 Aware）
- **THEN** 主进程通过 `webContents.send` 向渲染进程发送 `state-changed` 事件，渲染器通过 `contextBridge` 监听到事件后更新指示点颜色为蓝色脉冲并更新标题栏文本为"Frank - 检测中..."

#### Scenario: 渲染器响应式更新聊天面板
- **WHEN** 主进程转发状态变更事件为 Chat
- **THEN** 渲染器更新标题栏文本为"Frank - 对话中"，指示点变为紫色脉冲，输入框占位文本变为"正在听..."

#### Scenario: 无轮询验证
- **WHEN** 状态未发生变更
- **THEN** 渲染进程不发起任何轮询请求，UI 保持不变
