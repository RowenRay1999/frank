## MODIFIED Requirements

### Requirement: 设置面板占位

系统 MUST 提供一个设置面板，可从底部工具栏"⚙ 设置"按钮或展开模式侧边栏进入。设置面板内容区域 SHALL 包含功能性设置表单（非占位文本），支持 LLM、TTS、音频设备、摄像头设备、隐私策略等配置项的读取与修改。

设置面板 SHALL 通过 `settings.get` WebSocket 消息加载当前配置，通过 `settings.update` 消息提交变更。加载期间显示加载动画，保存成功显示"已保存"提示。

#### Scenario: 从工具栏打开设置面板

- **WHEN** 用户点击工具栏的"⚙ 设置"按钮
- **THEN** 设置面板显示，自动加载当前系统配置并填充表单字段

#### Scenario: 从侧边栏打开设置面板

- **WHEN** 用户处于全模式并在侧边栏点击"⚙️ 设置"入口
- **THEN** 设置面板显示，自动加载当前系统配置

#### Scenario: 修改配置项自动保存

- **WHEN** 用户修改任意配置项（如拖动温度滑块）
- **THEN** 系统自动发送 `settings.update` 提交变更，成功后短暂显示"已保存"

---

## ADDED Requirements

### Requirement: 人物面板入口扩展

底部工具栏 SHALL 新增"🎭 人物"按钮（btn-persona），位于"👥 成员"按钮之前。展开模式侧边栏 SHALL 新增"🎭 人物"导航项，位于"👤 成员"和"⚙️ 设置"之间。

#### Scenario: 人物按钮在工具栏可见

- **WHEN** 应用启动
- **THEN** 底部工具栏显示 4 个按钮：📋 任务、🎭 人物、👥 成员、⚙ 设置

#### Scenario: 侧边栏包含人物导航项

- **WHEN** 窗口处于全模式（展开模式）
- **THEN** 侧边栏导航项包含"🎭 人物"条目

### Requirement: 设置面板 WebSocket 通信

设置面板 SHALL 通过 `window.frankAPI.sendMessage()` 发送 `settings.get` 和 `settings.update` WebSocket 消息到 Python 后端。面板 SHALL 监听对应的响应消息以更新 UI 状态。

Python 后端 SHALL 处理以下消息：
- `settings.get`：返回当前 `config/frank.yaml` 的完整配置（API key 等敏感字段脱敏）
- `settings.update`：接受部分配置对象，深度合并写入 YAML 文件，返回更新后的全量配置

#### Scenario: 设置面板加载时获取配置

- **WHEN** 设置面板首次打开
- **THEN** 面板发送 `{ type: "settings.get" }`，等待响应后填充表单

#### Scenario: 配置更新写入文件

- **WHEN** 用户修改 LLM 温度参数
- **THEN** 面板发送 `{ type: "settings.update", payload: { llm: { temperature: 0.5 } } }`，后端合并写入 `config/frank.yaml`
