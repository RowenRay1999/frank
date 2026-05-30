## 1. 窗口自适应布局

- [x] 1.1 移除 `styles.css` 中的 `.phone-frame` 样式，将 `.main-stage` 改为 `width: 100vw; height: 100vh; border-radius: 0`
- [x] 1.2 修改 `body` 样式：从 `flex` 居中改为 `display: block`，背景保持 `var(--bg)`
- [x] 1.3 修改 `index.html`：移除 `.phone-frame` 包裹 `<div>`，`.main-stage` 直接作为 body 子元素
- [x] 1.4 更新 `main.js` 窗口配置：默认 800×600，`minWidth: 500, minHeight: 400`，`resizable: true`，移除 maxWidth/maxHeight
- [x] 1.5 设置 Zone 1（`.zone-status`）为窗口拖拽区域：`-webkit-app-region: drag`，内部交互元素 `no-drag`

## 2. 通用面板系统（PanelManager + .panel-slide）

- [x] 2.1 在 `styles.css` 中添加 `.panel-slide` 基础样式：absolute 定位覆盖 Zone 2、translateX 滑入动画、毛玻璃背景、z-index 30
- [x] 2.2 添加 `.panel-slide-header` / `.panel-slide-body` / `.panel-slide-footer` 样式
- [x] 2.3 在 `app.js` 中实现 `PanelManager` 对象：`open()` / `close()` / `closeAll()` / `isOpen()` 方法，单例互斥
- [x] 2.4 为 Chat Overlay（`#chatOverlay`）添加 `.panel-slide` 类，`openChat()` / `closeChat()` 委托给 PanelManager

## 3. Zone 3 导航栏面板化

- [x] 3.1 修改 `index.html` 中导航项 `<a>` 标签：`data-panel` 属性 + JS 事件监听拦截点击
- [x] 3.2 实现 `app.js` 中的 `openPanel(name)` 函数：根据名称映射到对应面板元素，调用 `PanelManager.open()`
- [x] 3.3 实现导航激活态联动：面板打开时对应导航项 `.active`，面板关闭时恢复默认（任务看板激活）
- [x] 3.4 修改通知预览按钮 onclick：从 `location.href` 改为触发通知面板
- [x] 3.5 修改任务列表"查看全部"链接：从 `<a href="tasks.html">` 改为触发任务详情面板

## 4. 设置面板迁移

- [x] 4.1 在 `index.html` Zone 2 中添加 `#settingsPanel` 面板 HTML（`.panel-slide` 结构），内嵌设置表单
- [x] 4.2 迁移设置表单内容：LLM 分组（API 地址/模型/温度/Token）、TTS 分组（语音角色/语速/音量）、音频设备分组（麦克风/唤醒词灵敏度）、摄像头分组（设备/人脸检测灵敏度）、隐私分组（自动清理/清理周期/通知天数）
- [x] 4.3 从旧 `styles.css` 提取表单控件样式并适配新令牌：`.settings-input`、`.settings-select`、`.settings-slider`、`.settings-toggle`、`.settings-section-title`、`.form-group`
- [x] 4.4 在 `app.js` 中移植设置面板 JS：`loadSettings()`、`populateSettingsForm()`、`flattenConfig()`、`unflattenConfig()`、保存状态管理、分组折叠、设备列表加载
- [x] 4.5 绑定设置表单事件：change 自动保存、input slider 实时显示、分组折叠点击

## 5. 成员管理面板迁移

- [x] 5.1 在 `index.html` Zone 2 中添加 `#membersPanel` 面板 HTML，包含：统计行、已识别成员列表区、待识别访客列表区、空状态提示、添加成员按钮
- [x] 5.2 从旧 `styles.css` 提取成员列表样式并适配：`.member-item`、`.member-info`、`.member-name`、`.member-meta`、`.member-avatar`、`.pending-item`、`.panel-stats`、`.empty-state`
- [x] 5.3 在 `app.js` 中移植成员面板 JS：`refreshMemberPanel()`、`renderMemberList()`、`renderPendingList()`、事件委托（编辑/删除/识别操作）
- [x] 5.4 绑定"添加成员"按钮 → 打开注册向导
- [x] 5.5 绑定 `identify` 操作 → `openIdentifyDialog()`（prompt 输入名称 + 角色选择）

## 6. 人物角色面板迁移

- [x] 6.1 在 `index.html` Zone 2 中添加 `#identityPanel` 面板 HTML，包含：身份识别卡、角色卡片区域、权限矩阵区域
- [x] 6.2 从旧 `styles.css` 提取角色面板样式并适配：`.identity-card`、`.identity-badge`、`.role-card`、`.role-card--owner`、`.role-card-header`、`.role-card-skills`、`.skill-tag`、`.permission-matrix`、`.perm-table`
- [x] 6.3 在 `app.js` 中移植角色面板 JS：`loadPersonaPanel()`、`renderRoleCards()`、`renderPermissionMatrix()`、`updateIdentityCard()`
- [x] 6.4 角色卡片点击展开/折叠技能详情交互

## 7. 注册向导迁移

- [x] 7.1 在 `index.html` body 末尾添加注册向导 Modal HTML（`#wizard-overlay`），4 步骤内容
- [x] 7.2 从旧 `styles.css` 提取向导样式并适配：`.wizard-overlay`、`.wizard`、`.wizard-header`、`.wizard-body`、`.wizard-footer`、`.progress-bar`、`.role-card-radio`、`.role-select-grid`
- [x] 7.3 在 `app.js` 中移植向导 JS：`openWizard()`、`closeWizard()`、`goToStep()`、步骤导航按钮事件、表单验证
- [x] 7.4 绑定向导 IPC 事件：`member.register_start`、`member.register_info`、`member.register_cancel`、`member.registered`（`onMemberRegistered`）

## 8. 任务详情面板

- [x] 8.1 在 `index.html` Zone 2 中添加 `#taskDetailPanel` 面板 HTML，包含：统计卡片行、筛选工具栏（状态筛选）、完整任务列表
- [x] 8.2 在 `app.js` 中实现 `renderTaskDetailList()`：渲染带进度条和状态标签的任务项，统计计数
- [x] 8.3 实现筛选功能和空状态

## 9. 通知面板

- [x] 9.1 在 `index.html` Zone 2 中添加 `#notifPanel` 面板 HTML，包含通知列表结构
- [x] 9.2 实现通知列表渲染：通知标题、正文、时间，空状态提示

## 10. 清理与验证

- [x] 10.1 移除旧 `.phone-frame` 相关样式和不必要的固定尺寸限制
- [x] 10.2 确保 Zone 3 导航栏不再使用 `href` 跳转到独立 HTML 页面
- [ ] 10.3 验证：窗口缩放时三区比例自适应、Orb 居中、任务列表和会话面板可见
- [ ] 10.4 验证：设置面板打开/关闭，表单控件修改并自动保存
- [ ] 10.5 验证：成员面板打开，成员列表渲染，添加成员→向导流程
- [ ] 10.6 验证：人物面板打开，角色卡片渲染，权限矩阵显示
- [ ] 10.7 验证：注册向导 4 步骤导航，表单验证
- [ ] 10.8 验证：Chat Overlay 与其他面板互斥，Escape/空格快捷键
- [ ] 10.9 验证：导航栏点击切换面板，激活态联动，关闭面板后恢复默认激活
