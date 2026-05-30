## ADDED Requirements

### Requirement: 可插拔 LLM Provider 抽象接口

Python 推理服务 SHALL 定义一个 `LLMProvider` 抽象基类，声明 `async generate(prompt, context) -> response` 异步接口。首批 SHALL 实现两个具体 Provider：`OpenAIProvider`（支持 OpenAI API 与 Azure OpenAI，通过 `base_url` 配置区分）和 `OllamaProvider`（通过 `http://localhost:11434` 调用本地 Ollama 服务）。

#### Scenario: 标准 LLMProvider 抽象基类定义

- **WHEN** 系统初始化 LLM 模块，从 `config/frank.yaml` 读取 `llm.provider` 配置项
- **THEN** 系统根据 `llm.provider` 值动态加载对应 Provider 实现：`"openai"` 或 `"azure"` 加载 `OpenAIProvider`，`"ollama"` 加载 `OllamaProvider`；若配置值不匹配任何已知 Provider，则抛出自定义 `UnsupportedProviderError` 异常并向 Electron 推送 `llm.error` 事件

#### Scenario: OpenAIProvider 支持 OpenAI 与 Azure OpenAI

- **WHEN** `llm.provider` 为 `"openai"` 且 `llm.base_url` 未设置（默认 `https://api.openai.com/v1`）
- **THEN** `OpenAIProvider` 使用 OpenAI 官方 API 端点，`api_key` 从 `FRANK_LLM_API_KEY` 环境变量读取，模型名称从 `llm.model` 配置读取

- **WHEN** `llm.provider` 为 `"azure"` 且 `llm.base_url` 设置为 `https://<resource>.openai.azure.com`
- **THEN** `OpenAIProvider` 使用 Azure OpenAI API 端点，通过 `api-version` 参数（默认 `2024-02-15-preview`）进行请求，`api_key` 使用 Azure OpenAI Key，模型部署名称从 `llm.model` 配置读取

#### Scenario: OllamaProvider 本地调用

- **WHEN** `llm.provider` 为 `"ollama"`
- **THEN** `OllamaProvider` 通过 HTTP POST 到 `http://localhost:11434/api/chat`，请求体包含 `model`（从 `llm.model` 读取，默认 `qwen2.5:7b`）、`messages`（对话历史）、`stream`（流式标志）、`options`（temperature 等参数）；响应解析遵循 Ollama API 格式，提取 `message.content` 作为回复文本

#### Scenario: Provider 初始化失败回退

- **WHEN** `OpenAIProvider` 初始化时因 API Key 缺失或无效抛出认证异常
- **THEN** 系统捕获异常，向 Electron 推送 `llm.warning` 事件，内容为 `"OpenAI API Key 无效或缺失，尝试切换到 Ollama 回退"`，并自动使用 `OllamaProvider` 作为当前会话的可用 Provider

---

### Requirement: 系统提示词自动注入

LLM 模块 SHALL 在每次请求时自动将系统提示词拼接到消息列表头部。系统提示词 SHALL 包含三部分：
1. **身份上下文**——当前用户的 `display_name`、`role`（来自身份模块）；
2. **可用能力列表**——Frank 当前注册的所有 Capability 名称与简短描述（如唤醒词可用的语音指令、视觉意图可识别的手势等）；
3. **对话准则**——回复应以中文为主、简洁且不过度解释、不确定时回答"我不确定"而非编造答案。

#### Scenario: 基本系统提示词拼接

- **WHEN** LLM 模块收到 `generate(prompt, context)` 调用，`context` 中包含 `display_name: "张明"`、`role: "owner"` 和已注册的 capabilities 列表
- **THEN** 系统在发送给 LLM 的消息列表头部插入系统消息，格式为：
  ```
  {
    "role": "system",
    "content": "你是一个智能助手 Frank。\n
    当前用户信息：\n
    - 称呼：张明\n
    - 角色：主人\n\n
    可用功能：\n
    - 语音对话：你可以与用户进行语音交流\n
    - 播放控制：暂停、继续、下一首（条件：媒体播放中）\n
    - 报时：告知当前时间\n
    - 音量调节：调高或调低音量（条件：正在说话）\n\n
    对话准则：\n
    - 请用中文回复，保持简洁（不超过 3 句话）\n
    - 不要过度解释或添加多余信息\n
    - 如果不知道答案，请说：'我不确定'\n
    - 不要编造事实"
  }
  ```

#### Scenario: capabilities 动态变化时系统提示词同步更新

- **WHEN** 用户在设置中增删免唤醒指令白名单条目（如新增"关闭灯光"），Frank 的 capabilities 列表发生变更
- **THEN** 下一次 LLM 请求时，系统提示词中的"可用功能"部分自动反映最新的 capabilities 列表，无需重启 Provider

#### Scenario: 角色权限影响系统提示词

- **WHEN** `context.role` 为 `"guest"`（访客角色）
- **THEN** 系统提示词中的对话准则额外追加："你当前与一位访客对话。注意不要透露主人的个人信息（如全名、日程安排、家庭地址）。"

---

### Requirement: 对话历史管理

LLM 模块 SHALL 维护一个每会话独立的对话历史列表，保留最近 N 轮（N 默认 10 轮，可在配置中通过 `llm.max_history_rounds` 调整）的用户/助手消息。每次生成回复前 SHALL 将历史消息注入上下文。当历史消息总 Token 数超过预算（默认 4096 tokens，由 `llm.max_history_tokens` 配置）时，SHALL 从最旧的消息开始逐轮丢弃，直到总 Token 数低于预算的 80%。

#### Scenario: 标准多轮对话历史记录

- **WHEN** 用户完成第 1 轮对话（用户说"现在几点了"→ 助手回复"现在是下午 3 点"）
- **THEN** 历史列表中追加 `{ "role": "user", "content": "现在几点了" }` 和 `{ "role": "assistant", "content": "现在是下午 3 点" }`，共 2 条消息

- **WHEN** 用户进行第 12 轮对话且 `max_history_rounds` 为默认值 10
- **THEN** 历史列表保留最近的 10 轮（20 条消息），最早的第 1 轮和第 2 轮消息被移除；后续请求中仅将保留的 20 条消息注入上下文

#### Scenario: Token 预算超限时从最早消息修剪

- **WHEN** 历史消息累积总 Token 数达到 4500，超过 `max_history_tokens` 的 4096 阈值
- **THEN** 系统从历史列表头部（最早消息）开始逐条移除消息，每移除一轮重新计算总 Token 数，直至总 Token 数 <= 4096 * 0.8 = 3276（预留 20% 给当前请求的 prompt 和输出）；被移除的消息不再参与后续对话上下文

#### Scenario: Token 计数使用 tiktoken

- **WHEN** LLM 模块需要计算历史消息的 Token 数
- **THEN** 使用 `tiktoken` 库的 `encoding_for_model()` 方法，根据当前 `llm.model` 选择对应编码器（如 `gpt-4` 使用 `cl100k_base`）；若模型不在 tiktoken 已知列表中，回退使用 `cl100k_base` 编码器进行近似估算

#### Scenario: 会话重置清空历史

- **WHEN** Electron 发送 `llm.reset` 控制指令，或唤醒词重新触发导致新会话开始
- **THEN** LLM 模块清空当前会话的历史消息列表，移除所有系统提示词之外的用户/助手消息，推送 `{ "type": "llm.history_cleared" }` 事件到 Electron

---

### Requirement: 流式响应

LLM 模块 SHALL 支持 Server-Sent Events (SSE) 流式响应。当 LLM Provider 返回流式响应时，SHALL 逐 Token 向 Electron 推送 `llm.token` 事件。当 LLM 完成全部生成后，SHALL 推送 `llm.response` 事件包含完整的回复文本。若 Provider 不支持流式（如某些本地 Ollama 配置），SHALL 在收到完整响应后一次性推送 `llm.response` 事件。

#### Scenario: OpenAI Provider 流式 Token 推送

- **WHEN** `OpenAIProvider.generate()` 设置 `stream=True`，LLM 开始返回 SSE 数据流，每个 chunk 包含 `delta.content` 片段
- **THEN** 对于每个非空的 `delta.content` 片段，系统立即向 Electron 推送 `{ "type": "llm.token", "token": <片段文本>, "index": <递增序号> }` 事件；`index` 从 0 开始单调递增，用于前端按序组装

#### Scenario: 流式响应完成时推送 llm.response

- **WHEN** LLM 返回 `[DONE]` 标志（OpenAI 格式）或 stream 迭代完毕（Ollama 格式为 `done: true` 标志）
- **THEN** 系统将收到的所有 token 拼接为完整回复文本，推送 `{ "type": "llm.response", "content": <完整回复文本>, "token_count": <总 token 数>, "provider": <当前 provider 名称> }` 事件到 Electron

#### Scenario: 流式中间出错时的降级

- **WHEN** SSE 流在传输过程中出现网络中断（如 `httpx.ReadError`），此时已推送部分 `llm.token` 事件但 LLM 未完成
- **THEN** 系统推送 `{ "type": "llm.error", "code": "STREAM_INTERRUPTED", "partial_content": <已收到的文本片段>, "recoverable": true }` 事件到 Electron，Electron 在 UI 中显示"回复被中断"提示并展示已收到的部分文本

#### Scenario: Ollama Provider 非流式回退

- **WHEN** Ollama API 请求中 `stream=false`，或 Provider 识别到当前模型不支持流式输出
- **THEN** 系统等待完整响应（HTTP 200 + JSON body），直接推送 `{ "type": "llm.response", "content": <完整回复文本>, "token_count": <总 token 数>, "provider": "ollama" }` 事件，不产生中间 `llm.token` 事件

---

### Requirement: Provider 自动回退

LLM 模块 SHALL 实现 Provider 回退机制。当主 Provider（配置中指定的 Provider）请求超时（默认 15 秒，由 `llm.timeout` 配置）或返回错误（HTTP 4xx/5xx、网络异常）时，SHALL 自动切换到 Ollama 本地回退 Provider。若 Ollama 回退也失败，SHALL 返回固定的离线回复文本："抱歉，我现在无法连接到语言服务。请检查网络后重试。"

#### Scenario: 主 Provider 超时触发 Ollama 回退

- **WHEN** `OpenAIProvider.generate()` 请求发送后 15 秒未收到完整响应（含流式首 token 超时）
- **THEN** 系统中断当前 Provider 请求，向 Electron 推送 `{ "type": "llm.fallback", "from_provider": "openai", "to_provider": "ollama", "reason": "timeout" }` 事件，随后使用 `OllamaProvider` 重新发送相同的 `prompt` 和 `context`

#### Scenario: 主 Provider HTTP 错误触发 Ollama 回退

- **WHEN** OpenAI API 返回 HTTP 429（速率限制）或 503（服务不可用）
- **THEN** 系统捕获 HTTP 错误，向 Electron 推送 `{ "type": "llm.fallback", "from_provider": "openai", "to_provider": "ollama", "reason": "http_503" }` 事件，回退到 Ollama Provider 重新请求

#### Scenario: Ollama 回退也失败时返回离线回复

- **WHEN** Ollama Provider 请求也出现超时或 HTTP 错误（如 Ollama 服务未运行、端口 11434 无响应）
- **THEN** 系统不调用任何 LLM，直接向 Electron 推送 `{ "type": "llm.response", "content": "抱歉，我现在无法连接到语言服务。请检查网络后重试。", "is_fallback_response": true }` 事件；该回复也被追加到对话历史中

#### Scenario: 回退后当前会话不再切换回主 Provider

- **WHEN** 主 Provider 超时回退到 Ollama 完成了一次对话
- **THEN** 当前会话剩余轮次继续使用 Ollama Provider；下一次唤醒触发新会话时，重新使用配置的主 Provider

#### Scenario: 配置中选择 Ollama 为主 Provider 时无回退

- **WHEN** `llm.provider` 配置为 `"ollama"` 且未设置 `llm.fallback_provider`
- **THEN** Ollama 是唯一 Provider，无回退机制；若 Ollama 请求失败，直接返回离线回复："抱歉，我现在无法连接到语言服务。请检查网络后重试。"

---

### Requirement: API Key 安全存储

LLM 模块 SHALL 从不将 API Key 写入 YAML 配置文件。API Key 的读取优先级为：1) 环境变量 `FRANK_LLM_API_KEY`；2) Windows Credential Manager（凭据管理器）中 `Frank/LLM_API_Key` 条目。Key 仅在运行时存在内存中，Provider 初始化完成后 SHALL 立即从内存中的临时变量清除原始字符串。

#### Scenario: 环境变量读取 API Key

- **WHEN** 系统启动时检测到环境变量 `FRANK_LLM_API_KEY` 已设置且非空
- **THEN** 系统从环境变量读取 API Key，用于初始化 `OpenAIProvider`，不进行额外存储；初始化完成后将原始环境变量值从临时变量中移除（`del` 操作）

#### Scenario: Windows Credential Manager 回退

- **WHEN** 环境变量 `FRANK_LLM_API_KEY` 未设置或为空，且 `llm.provider` 为 `"openai"` 或 `"azure"`
- **THEN** 系统通过 `keyring` Python 库调用 Windows Credential Manager API，检索 `Frank/LLM_API_Key` 通用凭据条目；若找到则使用其密码字段作为 API Key

#### Scenario: 凭据不存在时提示用户配置

- **WHEN** 环境变量和 Windows Credential Manager 中均未找到 API Key，且 Provider 为 `"openai"` 或 `"azure"`
- **THEN** 系统向 Electron 推送 `{ "type": "llm.api_key_missing", "provider": "openai" }` 事件；Electron 在 UI 中显示"请配置 LLM API Key"的对话框，引导用户设置环境变量或通过凭据管理器添加

#### Scenario: 配置 YAML 中禁止明文存储 Key

- **WHEN** 用户意外在 `config/frank.yaml` 的 `llm.api_key` 字段中填写了明文 Key
- **THEN** 系统在加载配置时检测到 `llm.api_key` 非空，向 Electron 推送 `{ "type": "llm.warning", "code": "API_KEY_IN_CONFIG", "message": "检测到 API Key 存储在配置文件中，请移除！安全存储方式请使用环境变量 FRANK_LLM_API_KEY 或 Windows 凭据管理器" }`，并忽略配置文件中的 Key，仍按优先级从环境变量和凭据管理器读取

---

### Requirement: 可配置 Provider 选择

Electron 主进程 SHALL 在 `config/frank.yaml` 中定义 `llm` 配置节。用户可在该配置节中设置 Provider 类型、模型名称、API 端点、超时时间等参数。配置变更在 LLM 模块重新初始化后生效（无需重启整个应用）。

#### Scenario: 标准 llm 配置节结构

- **WHEN** 用户打开 `config/frank.yaml` 查看 LLM 配置
- **THEN** 该文件包含如下 `llm` 配置节：
  ```yaml
  llm:
    provider: openai          # 可选值: openai, azure, ollama
    model: gpt-4o-mini        # 模型名称 / Azure 部署名称 / Ollama 模型名
    base_url: ""              # 自定义 API 端点（空=官方端点）
    api_key_env: FRANK_LLM_API_KEY  # API Key 环境变量名
    timeout: 15               # 请求超时秒数
    max_tokens: 2048          # 每次回复的最大 token 数
    temperature: 0.7          # 生成温度 (0.0-2.0)
    max_history_rounds: 10    # 保留的历史对话轮数
    max_history_tokens: 4096  # 历史消息最大 token 预算
    fallback_provider: ollama # 回退 Provider（空=不回退）
  ```

#### Scenario: Azure OpenAI 通过 base_url 区分

- **WHEN** `llm.provider` 设置为 `"azure"`，`llm.base_url` 设置为 `https://frank-openai.openai.azure.com`
- **THEN** `OpenAIProvider` 使用 `base_url` 作为 Azure OpenAI 资源端点，添加 `api-version` 查询参数（默认 `2024-02-15-preview`），`llm.model` 值作为 Azure 部署名称（deployment name）

#### Scenario: 配置热加载（需要重新初始化 Provider）

- **WHEN** 用户修改 `config/frank.yaml` 中 `llm` 节的任意字段并保存
- **THEN** Electron 文件监听器检测到配置变更，发送 `llm.reload` 指令到 Python 服务；Python 服务销毁当前 LLM Provider 实例，根据新配置重新初始化，然后推送 `{ "type": "llm.loaded", "provider": "openai", "model": "gpt-4o-mini" }` 事件；当前会话对话历史被保留，但下次请求使用新的 Provider

#### Scenario: 配置校验——非法 Provider 值

- **WHEN** 用户将 `llm.provider` 设置为 `"claude"`（不在 `["openai", "azure", "ollama"]` 中）
- **THEN** 系统在配置加载阶段抛出配置校验错误，向 Electron 推送 `{ "type": "llm.error", "code": "INVALID_PROVIDER", "message": "不支持的 Provider: claude，可选值为 openai, azure, ollama", "recoverable": true }`；LLM 模块进入待配置状态，不加载任何 Provider

#### Scenario: 配置校验——temperature 越界

- **WHEN** 用户将 `llm.temperature` 设置为 `3.5`（超出 0.0-2.0 范围）
- **THEN** 系统在校验阶段自动将 temperature 钳制到有效范围边界值 `2.0`，向 Electron 推送 `{ "type": "llm.warning", "code": "CLAMPED_VALUE", "field": "temperature", "original": 3.5, "clamped_to": 2.0 }` 事件
