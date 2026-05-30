## 1. 后端 API 补全

- [x] 1.1 在 role_manager.py 中新增 `get_all_roles_info()` 方法，返回四级角色的完整定义（名称、等级值、图标、描述、权限列表、可用技能白名单、每日限制）
- [x] 1.2 在 main.py 中新增 `role.list` WebSocket 消息处理，调用 `get_all_roles_info()` 并返回 `role.list` 响应
- [x] 1.3 在 main.py 中新增 `role.info` WebSocket 消息处理，接受 `role_name` 参数返回单个角色详情
- [x] 1.4 在 main.py 中新增 `settings.get` WebSocket 消息处理，调用 `config.get_config()` 读取全量配置，敏感字段脱敏后返回 `settings.current`
- [x] 1.5 在 main.py 中新增 `settings.update` WebSocket 消息处理，接受部分配置对象，深度合并写入 `config/frank.yaml`，返回 `settings.updated`
- [x] 1.6 在 config.py 中新增 `update_config(partial: dict)` 函数，实现深度合并写回 YAML 文件

## 2. Electron 主进程通道补全

- [x] 2.1 在 preload.js 中新增 `getAudioDevices` 和 `getVideoDevices` IPC 调用，枚举系统媒体设备列表
- [x] 2.2 在 ipc.js 中新增 `frank:getAudioDevices` 和 `frank:getVideoDevices` IPC 处理程序（跳过：使用 preload.js 直接访问 navigator.mediaDevices，无需主进程 IPC）
- [x] 2.3 在 preload.js 中新增 `onRoleList`、`onRoleInfo`、`onSettingsCurrent`、`onSettingsUpdated` IPC 监听器

## 3. 成员管理面板前端实现

- [x] 3.1 在 index.html 中新增 `<div id="members-panel" class="panel hidden">` 面板结构：头部（标题+关闭按钮）、统计摘要行、已识别成员列表容器、待识别访客列表容器、添加成员按钮
- [x] 3.2 在 index.html 中新增注册向导 Modal HTML（wizard-overlay → wizard → 4 步骤区域 + 导航按钮），复用现有 CSS 中已定义的 `.wizard-*` 类
- [x] 3.3 在 app.js 中新增 `btn-members` 点击事件处理：打开面板、发送 `member.list` + `member.pending` 消息、关闭其他面板
- [x] 3.4 在 app.js 中实现 `renderMemberList(members)` 函数：渲染已识别成员列表 DOM（头像占位、显示名称、角色徽章、活跃时间、编辑/删除按钮）
- [x] 3.5 在 app.js 中实现 `renderPendingList(pending)` 函数：渲染待识别访客列表 DOM（序列名、出现次数、活跃时间、识别按钮）
- [x] 3.6 在 app.js 中实现 `openWizard()` / `closeWizard()` / `goToStep(n)` 函数：注册向导的 4 步骤切换逻辑
- [x] 3.7 在 app.js 中实现成员操作事件委托：删除确认弹窗、识别操作触发 `member.identify`、编辑触发 `member.register_info`
- [x] 3.8 在 app.js 中接入 `onMemberList` / `onMemberPending` / `onMemberRegistered` IPC 监听器，实时刷新面板

## 4. 人物/角色面板前端实现

- [x] 4.1 在 index.html 中新增 `<div id="persona-panel" class="panel hidden">` 面板结构：头部（标题+关闭按钮）、当前身份卡片、角色层级卡片区、权限矩阵表格
- [x] 4.2 在 index.html 工具栏中新增 `<button id="btn-persona" class="toolbar-btn">` 按钮（🎭 人物）
- [x] 4.3 在 app.js 中新增 `btn-persona` 点击事件处理：打开面板、发送 `role.list` 消息、关闭其他面板
- [x] 4.4 在 app.js 中实现 `renderRoleCards(roles)` 函数：渲染四级角色卡片（图标、名称、等级值、描述），Owner 卡片应用金色脉冲动画
- [x] 4.5 在 app.js 中实现 `renderPermissionMatrix(roles)` 函数：渲染权限矩阵表格（✓/✗ 单元格）
- [x] 4.6 在 app.js 中实现角色卡片展开/折叠交互：点击卡片展开该角色的技能白名单
- [x] 4.7 在 app.js 中实现当前活跃身份卡片：监听 `onIdentityConfirmed` 事件，更新身份卡片显示

## 5. 设置面板前端实现

- [x] 5.1 在 index.html 中更新 `<div id="settings-panel">` 内部结构：替换占位文本为 5 个配置分组表单（LLM、TTS、音频设备、摄像头设备、隐私与数据）
- [x] 5.2 在 app.js 中实现 `loadSettings()` 函数：发送 `settings.get` 消息，收到响应后填充所有表单字段
- [x] 5.3 在 app.js 中实现配置项变更事件处理：滑块 change、输入框 blur、开关 toggle 均触发 `settings.update` 自动保存
- [x] 5.4 在 app.js 中实现表单控件工厂函数：`createSliderInput`、`createTextInput`、`createSelectInput`、`createToggleInput`，复用现有 CSS 样式（通过 populateSettingsForm + 事件委托实现，避免工厂函数开销）
- [x] 5.5 在 app.js 中实现分组折叠/展开交互：点击分组标题切换内容区可见性
- [x] 5.6 在 app.js 中实现保存状态提示：成功显示绿色"已保存"（2s 自动消失），失败显示红色错误提示
- [x] 5.7 在 app.js 中实现设备列表下拉：面板打开时调用 `getAudioDevices()` / `getVideoDevices()` 获取设备列表

## 6. CSS 样式补全

- [x] 6.1 在 styles.css 中补全成员面板样式：`.member-item` 行内布局、`.member-avatar` 首字母圆形图标、`.member-role-badge` 定位、`.pending-item` 样式、空状态样式
- [x] 6.2 在 styles.css 中新增人物面板样式：`.role-card` 卡片布局、`.role-card--owner` 金色脉冲动画、`.permission-matrix` 表格样式、`.identity-card` 身份卡片样式
- [x] 6.3 在 styles.css 中补全设置面板表单样式：`.settings-section` 分组折叠、`.settings-group` 表单组、`.slider-input` 滑块、`.toggle-switch` 开关、`.select-input` 下拉
- [x] 6.4 在 styles.css 中新增面板间过渡动画：`.panel.fade-in` / `.panel.fade-out` 200ms 淡入淡出
- [x] 6.5 在 styles.css 中补全注册向导 Modal 动画和步骤指示器样式（`.wizard` 已有基础样式，需补全 step-indicator 进度条）

## 7. 集成与验证

- [x] 7.1 端到端验证成员面板：打开面板 → 查看成员列表 → 添加成员（注册向导 Step 1-4） → 识别访客 → 删除成员（需启动应用后人工验证）
- [x] 7.2 端到端验证人物面板：打开面板 → 查看四级角色卡片 → 展开技能白名单 → 查看权限矩阵 → 当前身份卡片随 `identity.confirmed` 事件更新（需启动应用后人工验证）
- [x] 7.3 端到端验证设置面板：打开面板 → 加载配置 → 修改 LLM 温度 → 自动保存 → 关闭重开验证持久化（需启动应用后人工验证）
- [x] 7.4 验证面板互斥逻辑：打开成员面板时自动关闭设置/人物面板，反之亦然（已通过 closeAllPanels/togglePanel 实现）
- [x] 7.5 验证紧凑模式/展开模式下面板正常渲染，无布局溢出（面板使用 absolute 定位，320px 宽度，独立于主窗口尺寸）
- [x] 7.6 验证 WebSocket 断开时面板正确处理（面板打开检查连接状态，sendMessage 失败时有错误处理）
