## Context

Frank 是一个 Electron + Python 桌面应用，前端使用原生 HTML/CSS/JS（无框架），通过 Electron 主进程作为 WebSocket 客户端连接到 Python 推理服务（`ws://localhost:8765`）。渲染进程通过 `contextBridge`（preload.js）暴露的 `window.frankAPI` 与主进程通信。

当前三个管理界面均为空白占位：
- **设置面板**：有切换逻辑但内容仅为占位文本，无配置读写通道
- **成员面板**：工具栏按钮无事件处理，无面板 HTML，但后端 7 个 WebSocket API 已完全实现，CSS 样式已预定义
- **人物/角色面板**：无按钮、无面板、无后端 API（虽然后端 role_manager 已实现角色体系）

## Goals / Non-Goals

**Goals:**
- 为成员管理面板补全 HTML 结构、事件处理、WebSocket 通信，连接已有后端 API
- 新增人物/角色管理界面（工具栏按钮 + 面板 + 后端 API）
- 将设置面板从占位文本升级为功能表单，支撑 LLM、TTS、设备、隐私配置
- 所有新增 UI 遵循现有代码风格（原生 JS DOM 操作，无框架引入）

**Non-Goals:**
- 不引入前端框架（Vue/React）——保持与现有 codebase 一致
- 不修改现有管线（音频、摄像头、状态机、手势等）
- 不实现注册流程向导的实时摄像头预览——Step 2-4 的视觉反馈依赖后端事件推送，前端仅做状态展示
- 不修改数据库 schema——利用现有 members 表和 config 模块

## Decisions

### D1: 通信模式沿用现有 WebSocket 直连模式

**选择**：渲染进程通过 `window.frankAPI.sendMessage()` 发送 WebSocket 消息到 Python 后端，后端处理后返回响应消息。主进程仅做透明转发。

**备选方案**：新增 IPC 专用通道（`ipcRenderer.invoke` → 主进程处理）。**不采用**，因为：
- 成员管理已有 7 个 WebSocket API 就绪，改用 IPC 需要重写后端
- 设置读写直接操作 YAML 配置文件，Python 端已有 `config.py` 模块

**实现**：
- 成员相关：复用现有 `member.*` WebSocket 消息（已实现）
- 角色相关：新增 `role.list`、`role.info` WebSocket 消息
- 设置相关：新增 `settings.get`、`settings.update` WebSocket 消息

### D2: 面板架构采用面板切换模式

**选择**：在 `index.html` 中预定义三个面板 DIV（settings-panel、members-panel、persona-panel），通过 CSS `hidden` 类切换可见性。每个面板独立管理自己的 DOM 和事件。

**备选方案**：动态创建/销毁面板 DOM。**不采用**，因为：
- 原生 JS 无虚拟 DOM，频繁创建销毁性能差
- 预定义面板与现有 settings-panel 模式一致

**面板间互斥**：同一时间仅一个面板可见。打开新面板时关闭当前面板。

### D3: 设置持久化策略

**选择**：设置通过 Python 后端写入 `config/frank.yaml`，前端通过 `settings.get` 获取全量配置，通过 `settings.update` 提交部分更新。Python 端负责合并写入 YAML 文件。

**备选方案**：Electron 主进程直接读写 YAML。**不采用**，因为：
- Python 端已有完整的配置加载/缓存/默认值逻辑
- 保持单一配置源，避免 Electron 和 Python 配置不一致

**配置分组**：LLM 参数、TTS 设置、音频设备、摄像头设备、隐私策略

### D4: 人物面板信息来源

**选择**：人物面板展示静态角色体系信息（四级角色、权限矩阵）+ 动态当前活跃身份。后端新增 `role.list`（返回所有角色定义）和 `role.info`（返回指定角色详情）。当前活跃身份复用已有 `identity.get` 消息。

**备选方案**：仅在面板中硬编码角色信息。**不采用**，因为后端 role_manager 已定义完整的角色枚举、名称、徽章、权限映射，前端应单一数据源。

## Risks / Trade-offs

- **[R1] WebSocket 连接未就绪时面板打开失败** → 面板打开时检查连接状态（已有 `getConnectionStatus` API），未连接时显示"正在连接服务..."并自动重试
- **[R2] 设置写入 YAML 后需重启生效的配置项** → 设置面板对需重启项标注"重启后生效"，更新成功后显示提示
- **[R3] 成员面板数据量大时渲染性能** → 成员列表默认显示最近 20 条，提供"加载更多"；待识别访客按 last_active_at 降序排列，默认 10 条
- **[R4] 人物面板敏感信息暴露** → Guest 角色用户打开人物面板时仅显示角色名称和基础描述，不暴露 Owner/Adult 成员信息
