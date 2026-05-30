## 1. 设计令牌与样式基础

- [x] 1.1 重写 `styles.css`：建立 `:root` 设计令牌体系（原始色值 + 语义令牌），替换所有旧 CSS 变量
- [x] 1.2 定义间距刻度（`--space-1` ~ `--space-5`）、字体（`--font-display` / `--font-mono` / `--text-xs` ~ `--text-md`）、圆角（`--radius-sm` ~ `--radius-full`）、动效（`--motion-fast` ~ `--motion-slow` / `--ease-standard`）令牌
- [x] 1.3 实现基础重置样式（`* { margin:0; padding:0; box-sizing:border-box }`）、body 深色背景（`#0a0a0c`）、flex 居中布局、窗口拖拽区域（`-webkit-app-region`）
- [x] 1.4 定义 phone-frame 容器样式：390×844px 固定尺寸、40px 圆角、多层 box-shadow、overflow:hidden

## 2. Zone 3 — 底部导航栏

- [x] 2.1 在 `index.html` 中替换旧 `#toolbar` 为 `.zone-routing` 导航栏结构（5 个导航项 `<a>` 标签 + 分隔线 `<div>`），SVG 图标内联
- [x] 2.2 实现导航项样式：纵向 flex（图标+标签）、默认/悬停/激活三态、分隔线竖线、毛玻璃效果
- [x] 2.3 设置默认激活项为"任务看板"（`.active`），其他导航项 `href` 指向对应页面

## 3. Zone 2 布局与 Orb 动画

- [x] 3.1 替换旧 `#welcome-card` / `#chat-area` / `#input-area` 为 `.zone-monitor` 弹性容器结构
- [x] 3.2 实现 Orb 光球 HTML 结构：`.orb-stage` > `.thinking-rings`（3 光环）+ `.particle-field`（8 粒子）+ `.orb`（主光球）
- [x] 3.3 实现 Orb 光球 CSS：5 色阶 `radial-gradient` 同心环、外发光+内发光 box-shadow、88px 尺寸
- [x] 3.4 实现 Orb 动画关键帧：`orb-breathe-rings`（呼吸 3.2s idle / 2.4s thinking）、`orb-think`（scale 波动 1.8s）
- [x] 3.5 实现光环扩散动画：`ring-expand`（scale 0.75→1.6, opacity 0.55→0, 2.4s），3 个光环交错延迟（0s / 0.8s / 1.6s）
- [x] 3.6 实现粒子场动画：`particle-float`（translate+opacity+scale, 3s），8 个粒子不同位置和延迟
- [x] 3.7 实现状态标签（`.agent-label`）：脉冲圆点 + 文字，内容随状态变化（"聆听中·等待唤醒" / "对话中·正在响应" / "思考中·分析中"）
- [x] 3.8 实现 Orb 悬停/点击交互：hover scale(1.06)、active scale(0.95)、click 打开 Chat Overlay
- [x] 3.9 实现 `.monitor-thinking` 区域比例变化：`full` 态 flex-basis 30%、`collapsed` 态 flex:1

## 4. Zone 1 — 状态通知栏

- [x] 4.1 替换旧 `#title-bar` 为 `.zone-status` 双行布局 HTML 结构：上行用户身份+时间+通知、下行硬件芯片
- [x] 4.2 实现上行样式：用户头像（28px 圆形+首字符）、用户名称+角色、实时时钟（`setInterval` 每 10 秒更新）、通知预览按钮
- [x] 4.3 实现下行硬件芯片：CAM / MIC / SCR 三个 `.hw-chip`，默认灰色，激活态橙色+发光
- [x] 4.4 实现 Zone 1 毛玻璃效果和底部边框分隔线

## 5. Zone 2 下部 — 任务列表与会话面板

- [x] 5.1 实现 `.monitor-bottom` HTML 结构：`.section-header` + `.task-list-scroll` + `.task-half-hint` + `.convo-section`
- [x] 5.2 实现任务列表区域头部（标题"执行状态"、计数徽章、查看全部链接、3态切换按钮）
- [x] 5.3 实现任务行样式：4列 grid、4种状态图标（running/pending/done/failed）、spinner 动画、状态脉冲动画
- [x] 5.4 实现 3 态折叠切换 JS 逻辑（`cycleTaskState`）：collapsed → half → full → collapsed 循环，对应 CSS class 和箭头旋转
- [x] 5.5 实现半展开提示 `.task-half-hint` 点击展开逻辑
- [x] 5.6 实现会话展示栏 `.convo-bar`：Frank 头像、会话主题、元信息、展开按钮
- [x] 5.7 实现对话气泡内联预览 `.convo-bubbles`：frank/user 两种气泡样式、气泡进入动画、170px 最大高度滚动
- [x] 5.8 实现折叠态下任务列表和会话面板的显示/隐藏规则

## 6. Chat Overlay 对话浮层

- [x] 6.1 实现 `.chat-overlay` HTML 结构：头部（标题+关闭按钮）+ 消息区域 + 输入栏（输入框+发送按钮）
- [x] 6.2 实现 Overlay 滑入/滑出动画：`translateX(100%)` ↔ `translateX(0)`，400ms ease，毛玻璃背景+左阴影
- [x] 6.3 实现消息气泡样式：`.chat-bubble.frank`（左对齐深色）和 `.chat-bubble.user`（右对齐橙色），气泡进入动画 `bubble-in`
- [x] 6.4 实现输入栏交互：聚焦高亮（橙色边框+外发光）、Enter 发送、点击发送按钮
- [x] 6.5 实现 JS 交互逻辑：`openChat()` 打开、`closeChat()` 关闭、`sendMessage()` 添加用户气泡并清空输入
- [x] 6.6 实现键盘快捷键：Escape 关闭 Overlay、空格切换 Overlay（在 `document.body` 焦点时）

## 7. 窗口模型与主进程适配

- [x] 7.1 修改 `main.js` BrowserWindow 配置：固定尺寸 430×900、`resizable: false`、`frame: false`
- [x] 7.2 实现外置窗口控制条：phone-frame 外部左上角的半透明药丸形按钮（最小化、关闭），绑定 IPC 窗口操作
- [x] 7.3 添加返回首页链接（`.back-home`）到控制条旁
- [x] 7.4 保留系统托盘逻辑不变（显示/隐藏、退出）

## 8. app.js IPC 迁移与状态联动

- [x] 8.1 重写 DOM 引用层：所有 `getElementById` / `querySelector` 映射到新 HTML 结构
- [x] 8.2 迁移 `onStateChanged` IPC 回调：更新 Orb 动画状态（idle→breathing / chat→thinking）、Zone 1 状态标签文本
- [x] 8.3 迁移 `onIdentityConfirmed` IPC 回调：更新 Zone 1 用户头像、名称、角色
- [x] 8.4 迁移 `onFaceDetected` / `onFaceLost` IPC 回调：更新 Zone 1 CAM 硬件芯片激活/去激活状态
- [x] 8.5 迁移 `onWakeWord` IPC 回调：Orb 进入 thinking 动画态
- [x] 8.6 迁移 `onGestureDetected` IPC 回调：保留手势浮层 toast 和举手暂停横幅
- [x] 8.7 迁移 `onError` IPC 回调：保留错误 toast 显示
- [x] 8.8 迁移 `onVoiceStart` / `onVoiceEnd` IPC 回调：更新 MIC 硬件芯片状态
- [x] 8.9 实现实时时钟的 `updateTime()` 函数和 `setInterval` 定时器

## 9. 清理与验证

- [x] 9.1 移除旧 HTML 中不再需要的元素（`#title-bar`、`#welcome-card`、`#chat-area`、`#input-area`、`#toolbar`、`#settings-panel`、`#members-panel`、`#persona-panel`、`#wizard-overlay`）
- [x] 9.2 移除旧 CSS 中不再需要的样式规则（标题栏、欢迎卡片、工具栏、成员面板、设置面板、角色徽章、权限矩阵等）
- [x] 9.3 移除旧 JS 中不再需要的函数（`updateUI`、`addSystemMessage`、`togglePanel`、`closeAllPanels`、注册向导相关、设置面板相关、成员面板相关、人物面板相关）
- [x] 9.4 保留 CSS 中的手势浮层（`.gesture-toast`）、暂停横幅（`.pause-banner`）、错误提示（`.toast`）、滚动条样式（`::-webkit-scrollbar`）
- [ ] 9.5 启动应用验证：窗口以 430×900 呈现、phone-frame 居中、三区布局正确、Orb 呼吸动画播放
- [ ] 9.6 验证 IPC 通路：状态变更联动 Orb 动画、身份确认更新 Zone 1、唤醒词触发 thinking 动画
- [ ] 9.7 验证 Chat Overlay：点击 Orb 打开、Escape 关闭、输入消息发送、气泡样式正确
- [ ] 9.8 验证 3 态切换：collapsed → half → full 循环、箭头旋转、内容显隐正确
- [ ] 9.9 验证导航栏：导航项点击跳转、激活态高亮、悬停效果
