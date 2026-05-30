## ADDED Requirements

### Requirement: edge-tts 集成
Python TTS 模块 SHALL 使用 `edge-tts` 库调用 Microsoft Edge 免费 TTS 服务进行中文语音合成。默认语音为 `zh-CN-XiaoxiaoNeural`（女声），也可选择 `zh-CN-YunxiNeural`（男声），两者均可在配置中切换。

#### Scenario: 默认女声合成
- **WHEN** 配置文件中 `tts.voice` 未指定或设置为 `zh-CN-XiaoxiaoNeural`
- **THEN** Python 调用 `edge-tts` 的 `Communicate` 对象并以 `zh-CN-XiaoxiaoNeural` 作为 voice 参数，向 Microsoft Edge TTS 服务发起 SSML 合成请求，语音输出为自然中文女声

#### Scenario: 切换男声
- **WHEN** 用户在 `config/frank.yaml` 中将 `tts.voice` 设置为 `zh-CN-YunxiNeural`
- **THEN** Python TTS 模块在下一次合成时使用 `zh-CN-YunxiNeural` 语音，输出为自然中文男声

#### Scenario: 自定义语音
- **WHEN** 用户将 `tts.voice` 设置为其他 Microsoft Edge TTS 支持的语音标识符（如 `zh-CN-XiaoyiNeural`、`zh-CN-Liaoning-XiaobeiNeural` 等）
- **THEN** Python TTS 模块按指定语音标识符进行合成，不做白名单校验；若语音不存在，服务端推送 `tts.error` 事件并回退至默认语音

#### Scenario: 非中文文本自动回退
- **WHEN** LLM 回复中包含非中文文本（英文、数字、混合语言）
- **THEN** `edge-tts` 自动处理多语言混合合成（Microsoft Edge TTS 内置多语言能力），无需显式切换语音

---

### Requirement: TTS 合成与流式播放
Python TTS 模块 SHALL 将 LLM 回复文本合成为 MP3 音频流，并通过系统默认音频设备播放。支持边合成边播放的流式模式，无需等待完整音频生成。

#### Scenario: 标准合成与播放
- **WHEN** LLM 流式响应完成后，完整文本传递给 TTS 模块
- **THEN** TTS 模块调用 `edge-tts.Communicate(text, voice)` 建立 WebSocket 连接到 Microsoft Edge TTS 服务，接收 MP3 音频流，通过 PyAudio 或 `sounddevice` 以默认输出设备播放

#### Scenario: 流式播放（边合成边播）
- **WHEN** LLM 在流式模式下逐句（或按 SSML `<break>` 标记分段）传递文本块到 TTS 模块
- **THEN** TTS 模块对每个文本块独立发起 `edge-tts` 请求，每收到一个音频 chunk 即写入音频输出缓冲区，前一块音频播放的同时后一块在后台合成中；块间无缝衔接，用户感知为连续语音

#### Scenario: 选择默认音频输出设备
- **WHEN** Python TTS 模块初始化时
- **THEN** 通过 `sounddevice.query_devices()` 或 PyAudio 枚举系统音频输出设备，选择 `host_api` 的设备索引 0 或 `frank.yaml` 中 `tts.output_device_id` 指定的设备作为播放设备；找不到可用输出设备时推送 `tts.error` 事件 `{ "code": "NO_OUTPUT_DEVICE" }`

#### Scenario: 播放音量控制
- **WHEN** 用户在配置中设置 `tts.volume` 为 `0.8`（范围 0.0-1.0）
- **THEN** Python 在播放前将 MP3 解码为 PCM 并应用线性增益缩放（`pcm * 0.8`），限制峰值不超过 int16 范围（-32768 至 32767）以防止削波失真

#### Scenario: 文本过长时分段合成
- **WHEN** LLM 回复文本超过 1000 个字符
- **THEN** TTS 模块按句号、感叹号、问号、换行符分割为多个短句，对每个短句分别发起 `edge-tts` 合成请求，依次放入播放队列；用户感知为连续语音而非逐句停顿

---

### Requirement: TTS 事件推送
Python TTS 模块在合成与播放的全生命周期中 SHALL 向 Electron 推送 `tts.start`、`tts.progress` 和 `tts.complete` 事件，以便 UI 显示状态反馈（语音指示图标、播放进度等）。

#### Scenario: TTS 开始播放
- **WHEN** LLM 回复文本首次传入 TTS 模块且首个音频 chunk 即将播放
- **THEN** Python 向 Electron 推送 `{ "type": "tts.start", "text_length": <回复文本字符数>, "voice": "zh-CN-XiaoxiaoNeural", "estimated_duration": <预估时长秒> }`，Electron 更新状态机至 Speaking 子状态并显示语音播放指示

#### Scenario: TTS 播放进度
- **WHEN** TTS 每播放完一个分段（或每经过 1 秒播放时间）
- **THEN** Python 向 Electron 推送 `{ "type": "tts.progress", "segment_index": <当前分段序号>, "segments_total": <总分段数>, "elapsed": <已播放秒数>, "remaining": <剩余预估秒数> }`，Electron 在对话气泡上显示播放进度条

#### Scenario: TTS 播放完成
- **WHEN** 所有分段播放完毕且音频输出流关闭
- **THEN** Python 向 Electron 推送 `{ "type": "tts.complete", "total_duration": <总播放时长秒>, "segments_played": <实际播放分段数> }`，Electron 将状态机从 Speaking 回退至 Listening 或 Idle（取决于配置的持续交互模式）

#### Scenario: TTS 事件与状态机联动
- **WHEN** Electron 收到 `tts.start` 事件且当前状态为 Chat.Thinking
- **THEN** Electron 立即将状态机切换至 Chat.Speaking，UI 展示语音播放动画和助手消息气泡
- **WHEN** Electron 收到 `tts.complete` 事件
- **THEN** Electron 根据 `frank.yaml` 中 `conversation.continuous_mode` 配置决定下一状态：`true` 则回到 Chat.Listening 开始下一轮对话，`false` 则退出 Chat 状态回到 Idle

---

### Requirement: TTS 降级处理
当 `edge-tts` 服务不可用时（网络故障、服务端错误、超时等），Python TTS 模块 SHALL 自动重试 2 次，若均失败则降级为纯文本回复模式，并向 Electron 推送 `tts.unavailable` 事件。

#### Scenario: 网络超时重试
- **WHEN** `edge-tts` 发起 WebSocket 连接后在 10 秒内未收到服务端响应（`asyncio.TimeoutError`）
- **THEN** Python 记录日志 `WARNING: edge-tts 连接超时（第 1 次）`，等待 1 秒后重试；第二次再次超时则等待 2 秒后重试；三次均失败则推送 `{ "type": "tts.unavailable", "reason": "timeout", "retries": 2 }` 并降级

#### Scenario: HTTP 服务端错误重试
- **WHEN** Microsoft Edge TTS 服务返回 HTTP 503（Service Unavailable）或 429（Too Many Requests）
- **THEN** Python 记录日志 `WARNING: edge-tts 服务端错误 503（第 1 次）`，等待 2 秒后重试；第二次仍失败则等待 4 秒后重试；第三次失败则推送 `{ "type": "tts.unavailable", "reason": "service_error", "status_code": 503, "retries": 2 }` 并降级

#### Scenario: 非可恢复错误不重试
- **WHEN** `edge-tts` 抛出非网络类异常（如 SSML 格式错误、参数校验失败）
- **THEN** Python 识别为不可恢复错误，不执行重试，立即推送 `{ "type": "tts.unavailable", "reason": "invalid_parameters", "retries": 0 }` 并降级

#### Scenario: 降级后纯文本回复
- **WHEN** TTS 降级为不可用状态（已推送 `tts.unavailable`）
- **THEN** Python TTS 模块跳过所有合成与播放逻辑，LLM 回复仅以文本形式通过 Electron 渲染在聊天面板中；对话不中断，用户可读取文字回复

#### Scenario: 降级后自动恢复尝试
- **WHEN** TTS 处于降级状态，且下一次对话需要回复
- **THEN** Python 尝试重新连接 edge-tts 服务一次；若成功则推送 `{ "type": "tts.available" }` 恢复正常 TTS 播放，若失败则继续降级并在日志记录 `INFO: edge-tts 仍不可用，保持 text-only 模式`

---

### Requirement: 可配置语音设置
`config/frank.yaml` SHALL 包含 `tts` 配置段，支持语音选择、语速（0.5-2.0）和音调设置。配置更改在下一轮 TTS 合成时生效，无需重启服务。

#### Scenario: 读取完整 TTS 配置
- **WHEN** Python 服务启动时解析 `config/frank.yaml`
- **THEN** 读取 `tts` 段配置：`{ "voice": "zh-CN-XiaoxiaoNeural", "speed": 1.0, "pitch": 0, "volume": 1.0, "output_device_id": null }`；缺失的字段使用默认值，不阻塞服务启动

#### Scenario: 语速配置生效
- **WHEN** 用户将 `tts.speed` 设置为 `1.5`
- **THEN** Python 在每次合成请求的 SSML 中插入 `<prosody rate="+50%">` 标签，edge-tts 按 1.5 倍速合成音频；取值范围 0.5（-50%）到 2.0（+100%），超出范围时 clamp 到边界值

#### Scenario: 音调配置生效
- **WHEN** 用户将 `tts.pitch` 设置为 `+2`
- **THEN** Python 在每次合成请求的 SSML 中插入 `<prosody pitch="+2st">` 标签，edge-tts 按升高 2 个半音合成音频；取值范围 -12 到 +12（半音），超出范围时 clamp 到边界值

#### Scenario: 配置动态热更新
- **WHEN** 用户在运行中通过 Electron 设置面板修改 `tts.voice` 从女声切换为男声
- **THEN** Electron 通过 WebSocket 发送 `{ "type": "config.update", "path": "tts.voice", "value": "zh-CN-YunxiNeural" }` 到 Python；Python 更新内存中的配置对象，下一次 TTS 合成立即使用新语音，无需重启服务

#### Scenario: 男声/女声快捷切换
- **WHEN** 用户发送快捷指令 `"换男声"` 或 `"换女声"`（通过免唤醒指令或 LLM 意图路由）
- **THEN** Python 将 `tts.voice` 在 `zh-CN-XiaoxiaoNeural` 和 `zh-CN-YunxiNeural` 之间切换，推送 `{ "type": "tts.voice_changed", "voice": "zh-CN-YunxiNeural" }` 事件到 Electron，并在聊天面板显示"已切换为 Yunxi 男声"提示

---

### Requirement: TTS 中断
在 TTS 播放过程中，若 VAD 检测到用户说话（`voice_start` 事件），Python 服务 SHALL 立即停止当前 TTS 合成与播放，清理音频缓冲区，并进入语音采集状态。

#### Scenario: 用户说话中断 TTS 播放
- **WHEN** TTS 正在播放中且状态机处于 Chat.Speaking，VAD 模块推送 `mic.voice_start` 事件
- **THEN** Python TTS 模块立即执行：a) 关闭当前 `edge-tts` WebSocket 连接，b) 停止音频输出流并清空播放缓冲区，c) 推送 `{ "type": "tts.interrupted", "interrupted_at": <已播放秒数> }` 事件到 Electron；状态机从 Chat.Speaking 切换至 Chat.Listening，开始采集用户新的语音输入

#### Scenario: 中断后原回复丢弃
- **WHEN** TTS 被用户说话中断
- **THEN** 原 LLM 回复的剩余音频不再播放，被丢弃；LLM 不会自动续播——用户新语音输入经 STT→LLM 流程后生成全新回复

#### Scenario: 中断后状态机回退
- **WHEN** Electron 收到 `tts.interrupted` 事件
- **THEN** Electron 将状态从 Chat.Speaking 切换为 Chat.Listening，UI 隐藏语音播放指示并显示麦克风波形动画，表示正在监听用户输入

#### Scenario: VAD 误触发不中断
- **WHEN** 环境噪音导致 VAD 短暂误报 `voice_start`（概率单次抖动，不满足 VAD 滞回确认条件）
- **THEN** TTS 播放不受影响，不执行中断逻辑；仅在 VAD 经滞回逻辑确认有效 `voice_start`（连续多帧超过阈值）后才触发中断

#### Scenario: 中断后新语音记录的完整性
- **WHEN** TTS 中断后状态机进入 Chat.Listening
- **THEN** 环形缓冲区保留当前及之前 1.5 秒的音频，TTS 中断前的环境音不会被误判为语音输入；VAD 从新 `voice_start` 时刻开始积累音频段，确保用户完整语音不丢失
