## ADDED Requirements

### Requirement: 设置面板表单布局

设置面板 SHALL 从占位文本升级为分组表单布局。面板内容区 SHALL 以分组（section）形式组织配置项，每组包含标题和若干配置项。面板 SHALL 支持纵向滚动。

配置分组 SHALL 为：
1. **大模型（LLM）**：API 地址、模型名称、温度、最大 Token 数
2. **语音合成（TTS）**：语音角色、语速、音量
3. **音频设备**：麦克风设备选择、唤醒词灵敏度
4. **摄像头设备**：摄像头设备选择、人脸检测灵敏度
5. **隐私与数据**：自动清理开关、清理周期、访客数据保留策略

#### Scenario: 打开设置面板查看分组

- **WHEN** 用户打开设置面板
- **THEN** 面板显示 5 个配置分组，每组可折叠/展开，默认展开前 3 组

#### Scenario: 分组折叠/展开

- **WHEN** 用户点击配置分组标题
- **THEN** 该分组的配置项折叠收起，再次点击展开

---

### Requirement: 配置读取

设置面板打开时 SHALL 通过 `settings.get` WebSocket 消息从后端获取当前全量配置。加载期间 SHALL 显示加载动画。加载失败 SHALL 显示错误提示并提供重试按钮。

#### Scenario: 面板打开时加载配置

- **WHEN** 用户打开设置面板
- **THEN** 面板发送 `{ type: "settings.get" }` 消息，收到响应后填充所有表单字段

#### Scenario: 加载失败显示重试

- **WHEN** `settings.get` 请求超时或返回错误
- **THEN** 面板显示"配置加载失败"提示和"重试"按钮

---

### Requirement: 配置修改与保存

用户修改配置项后 SHALL 通过 `settings.update` WebSocket 消息提交变更。系统 SHALL 支持单字段更新（发送变更的部分配置）。保存成功后 SHALL 显示"已保存"提示（2 秒后自动消失）。保存失败 SHALL 显示错误提示。

对需要重启生效的配置项（如设备选择），SHALL 在配置项旁标注"重启后生效"。

#### Scenario: 修改 LLM 温度参数

- **WHEN** 用户将温度滑块从 0.7 拖动到 0.5，松开滑块
- **THEN** 面板发送 `{ type: "settings.update", payload: { llm: { temperature: 0.5 } } }`，收到成功响应后显示"已保存"

#### Scenario: 保存失败提示

- **WHEN** `settings.update` 返回错误
- **THEN** 面板显示红色错误提示"保存失败：[错误信息]"

---

### Requirement: LLM 配置项

LLM 配置分组 SHALL 包含以下配置项：
- API 地址（文本输入，必填，默认 `https://api.openai.com/v1`）
- 模型名称（文本输入，必填，默认 `gpt-4o`）
- 温度（滑块，范围 0-2.0，步长 0.1，默认 0.7）
- 最大 Token 数（数字输入，范围 100-4096，默认 2048）
- 系统提示词（多行文本输入，可选）

#### Scenario: 修改 API 地址

- **WHEN** 用户在 LLM 分组中输入新的 API 地址并失焦
- **THEN** 面板自动保存新 API 地址到后端配置

---

### Requirement: TTS 配置项

TTS 配置分组 SHALL 包含以下配置项：
- 语音角色（下拉选择，从后端获取可用语音列表，默认"zh-CN-XiaoxiaoNeural"）
- 语速（滑块，范围 0.5-2.0，步长 0.1，默认 1.0）
- 音量（滑块，范围 0-100，步长 5，默认 80）

#### Scenario: 调整 TTS 语速

- **WHEN** 用户将语速滑块从 1.0 拖动到 1.3，松开滑块
- **THEN** 面板自动保存新语速设置

---

### Requirement: 设备选择配置项

音频设备分组 SHALL 包含麦克风设备下拉选择，选项从 `window.frankAPI.getAudioDevices()` 获取。摄像头设备分组 SHALL 包含摄像头设备下拉选择，选项从 `window.frankAPI.getVideoDevices()` 获取。

设备列表 SHALL 在面板打开时刷新，选中项高亮为当前活跃设备。设备变更 SHALL 标注"重启后生效"。

#### Scenario: 切换麦克风设备

- **WHEN** 用户在音频设备分组下拉中选择新麦克风
- **THEN** 面板保存设置，显示"麦克风已更改，重启后生效"

---

### Requirement: 隐私与数据配置项

隐私与数据分组 SHALL 包含以下配置项：
- 自动清理未识别访客（开关，默认开启）
- 清理周期（滑块/数字输入，范围 15-90 天，默认 30 天）
- 清理前通知天数（滑块，范围 0-7 天，默认 3 天）
- 保留频繁访客（出现 ≥ N 次免清理）（开关，默认开启，阈值默认 5 次）

#### Scenario: 关闭自动清理

- **WHEN** 用户关闭"自动清理未识别访客"开关
- **THEN** 清理周期和通知天数配置项灰化禁用，面板保存设置

---

### Requirement: 后端设置读写 API

Python 后端 SHALL 处理以下 WebSocket 消息：
- `settings.get`：返回当前全量配置（从 `config/frank.yaml` 读取）
- `settings.update`：接受部分配置对象，合并写入 `config/frank.yaml`，返回更新后的配置

`settings.get` 返回的配置 SHALL 过滤敏感字段（如 API key 仅返回前 4 位 + `****`）。

#### Scenario: settings.get 返回配置

- **WHEN** 前端发送 `{ type: "settings.get" }`
- **THEN** 后端返回 `{ type: "settings.current", payload: { llm: {...}, tts: {...}, audio: {...}, camera: {...}, privacy: {...} } }`

#### Scenario: settings.update 合并写入

- **WHEN** 前端发送 `{ type: "settings.update", payload: { llm: { temperature: 0.5 } } }`
- **THEN** 后端读取当前 YAML，深度合并 temperature 变更，写回文件，返回 `{ type: "settings.updated", payload: { llm: { temperature: 0.5 } } }`
