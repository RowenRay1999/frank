## Why

当前 Frank 桌面应用的三个核心管理界面——成员管理、角色/人物管理、系统设置——均无实际功能实现。成员管理的 7 个后端 API 已完全就绪但前端缺失面板和交互逻辑；角色人物管理缺少专用界面和 API 暴露；设置面板仅有占位文本无法修改任何配置。用户无法通过 UI 完成成员注册、角色查看、系统配置等基本操作，应用无法交付给实际家庭场景使用。

## What Changes

- **成员管理面板功能实现**：补全成员面板 HTML 结构，接入已有的 7 个 WebSocket 后端 API（member.list、member.pending、member.register_start/info/cancel、member.identify、member.delete），实现成员列表展示、待识别访客管理、成员识别与删除操作
- **角色/人物管理界面新增**：新增"人物"工具栏按钮和对应面板，展示系统角色的完整层级、权限说明和当前活跃用户身份信息，新增 `role.list` 和 `role.info` WebSocket API 端点
- **设置界面功能实现**：替换占位文本为实际设置表单，实现配置项的读取与持久化（LLM 参数、TTS 设置、音频/摄像头设备选择、隐私与数据策略），新增 `settings.get` 和 `settings.update` IPC/WebSocket 通道
- **IPC/WebSocket 通道补全**：为上述三个界面补全缺失的前后端通信通道，确保数据双向流动

## Capabilities

### New Capabilities
- `persona-panel`: 角色/人物管理界面——展示四级角色体系（Owner/Adult/Child/Guest）的层级结构、权限矩阵、当前活跃用户信息，支持查看各角色可用的技能白名单和每日使用限制
- `settings-panel`: 设置界面功能——替换占位文本为完整设置表单，支持 LLM 参数配置、TTS 语音选择、音频/摄像头设备选择、隐私数据策略配置、自动清理策略配置

### Modified Capabilities
- `member-management`: 前端面板从无到有——补全成员列表 HTML、事件处理 JS、WebSocket 消息收发，连接已实现的后端 API。spec 中已有的 UI 需求（面板布局、注册向导、成员操作）保持不变，本次改动为落实现有 spec 的前端实现
- `ui-shell`: 设置面板从占位升级为功能界面；工具栏新增"人物"按钮；展开模式侧边栏新增"人物"导航项。spec 中已定义的窗口管理、状态指示器、聊天面板等模块不受影响

## Impact

- **前端文件**：`src/electron/renderer/index.html`（新增成员面板 HTML、人物面板 HTML、设置面板表单）、`src/electron/renderer/app.js`（新增三个面板的事件处理、WebSocket 通信、DOM 渲染逻辑）、`src/electron/renderer/styles.css`（补全面板样式）
- **Electron 主进程**：`src/electron/main/preload.js`（新增 settings IPC 通道）、`src/electron/main/ipc.js`（新增 settings 读写处理）
- **Python 后端**：`src/python/server/main.py`（新增 role.list、role.info、settings.get、settings.update WebSocket 消息处理）、`src/python/modules/role/role_manager.py`（新增 get_all_roles_info 方法）
- **无破坏性变更**：所有改动为新增功能，不影响现有管线（音频、摄像头、状态机等）
