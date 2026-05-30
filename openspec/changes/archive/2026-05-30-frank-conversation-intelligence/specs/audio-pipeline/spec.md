## MODIFIED Requirements

### Requirement: 唤醒词检测

> 以下修改在原有需求基础上追加。若 Scenario 与基准规范中同名 Scenario 冲突，以本 DELTA 为准。

#### Scenario: 标准唤醒词检测（修改版）

- **WHEN** 用户说出 "Hey Frank"，OpenWakeWord 模型输出的置信度分数超过阈值 0.7
- **THEN** Python 向 Electron 推送 `mic.wake_word` 事件。若唤醒词所在语音段同时满足声纹提取条件（时长 >= 1.5 秒，SNR > 10dB，单说话人），则负载包含 `{ "confidence": 0.85, "timestamp": <采集时间戳>, "voiceprint_embedding": [192 维浮点数组], "voiceprint_duration": <语音段时长秒> }`；若不满足条件，则负载保持原有格式 `{ "confidence": 0.85, "timestamp": <采集时间戳> }`。事件推送后**SHALL 启动 STT 处理链**：从环形缓冲区提取 `trigger_pos - 24000 样本（1.5秒）` 开始到 VAD 检测到连续 0.5 秒静默为止的完整音频段，送入 STT 模块进行转录

---

## ADDED Requirements

### Requirement: STT 处理链

Python 推理服务在检测到唤醒词并推送 `mic.wake_word` 事件后 SHALL 启动 STT 处理链：从环形缓冲区提取从触发位置前 1.5 秒开始到 VAD 检测到连续 0.5 秒静默为止的完整音频段，将该音频段送入 STT（语音转文字）模块进行转录。转录完成后 SHALL 向 Electron 推送 `stt.transcription` 事件，包含转录文本及置信度信息。

#### Scenario: 唤醒词触发后 STT 转录流程

- **WHEN** 唤醒词检测成功，`mic.wake_word` 事件已推送，环形缓冲区中存在从 `trigger_pos - 24000 样本（1.5秒）` 开始到 VAD 检测到连续 0.5 秒静默为止的完整音频段
- **THEN** Python 服务将该音频段以 16kHz、16-bit 单声道 PCM 格式送入 STT 模块（如 Whisper 或类似引擎），STT 模块输出转录文本及置信度分数；转录完成后 Python 向 Electron 推送 `stt.transcription` 事件，负载包含 `{ "text": "帮我查一下明天的天气", "confidence": 0.92, "language": "zh", "duration": <语音段时长秒>, "timestamp": <音频段开始时间戳> }`

#### Scenario: STT 转录失败处理

- **WHEN** STT 模块返回空结果、置信度低于 0.3 或抛出异常（如音频段过短、模型加载失败、推理超时）
- **THEN** Python 推送 `stt.transcription` 事件，负载包含 `{ "text": "", "confidence": 0.0, "error": "TRANSCRIPTION_FAILED", "suggestion": "请重新说话" }`；Electron 在 UI 显示"未识别到有效语音，请重试"提示，不触发后续对话流程

#### Scenario: 免唤醒词触发 STT（连续对话模式）

- **WHEN** 系统处于 Chat 状态（即上一次唤醒词已触发且对话尚未结束），VAD 上报 `voice_end` 事件
- **THEN** Python 服务不等待唤醒词检测，直接从环形缓冲区提取从 `voice_start - 24000 样本（1.5秒）` 到 `voice_end` 位置的音频段，送入 STT 模块进行转录；转录结果以 `stt.transcription` 事件推送，负载格式与唤醒词触发的 STT 一致

#### Scenario: 转录文本空字符串

- **WHEN** STT 模块返回的转录文本为空字符串（如用户仅发出咳嗽声或环境噪音被误判为语音）
- **THEN** Python 推送 `stt.transcription` 事件，负载包含 `{ "text": "", "confidence": 0.0, "error": "EMPTY_TRANSCRIPTION", "suggestion": "未检测到有效语音内容" }`，Electron 不更新对话历史

#### Scenario: STT 模型热加载与重试

- **WHEN** 首次 STT 推理时模型尚未加载（如服务刚启动），加载时间可能超过预期
- **THEN** Python 在首次调用时加载 STT 模型，加载完成后对当前音频段执行转录；若加载耗时超过 3 秒，取消失败并推送 `stt.transcription` 事件，`error` 为 `"MODEL_LOAD_TIMEOUT"`，`suggestion` 为 `"语音模型加载中，请稍后再试"`

---

### Requirement: 连续聆听模式

在 Chat 状态下，Python 推理服务 SHALL 保持 VAD 持续活跃。当第一次唤醒词触发完成 STT 转录后，后续对话不再需要重复唤醒词。VAD 每次检测到 `voice_end` 事件时自动触发 STT 转录。该模式 SHALL 在满足任一退出条件时自动退出并回到唤醒词监听模式。

#### Scenario: 唤醒后连续对话

- **WHEN** 用户说"Hey Frank 帮我查天气"，唤醒词触发 STT 转录完成，系统进入 Chat 状态；随后用户未说唤醒词直接说"那明天呢"，VAD 检测到 `voice_start` → `voice_end`
- **THEN** 系统保持 VAD 活跃，不等待唤醒词，直接提取音频段送入 STT；转录结果 `{ "text": "那明天呢", ... }` 以 `stt.transcription` 事件推送，Electron 将该内容追加到当前对话上下文中

#### Scenario: 连续聆听超时退出

- **WHEN** Chat 状态下，最后一段语音结束（VAD 上报 `voice_end`）后持续静默达到 30 秒（由配置 `conversation.idle_timeout` 决定，默认 30 秒）
- **THEN** 系统自动退出连续聆听模式：停止 STT 自动转录，状态机回到等待唤醒词状态，并向 Electron 推送 `conversation.idle_timeout` 事件，负载包含 `{ "duration": 30, "message": "长时间未说话，已退出连续对话模式" }`

#### Scenario: 用户主动退出连续聆听

- **WHEN** Chat 状态下，用户说出退出指令（如"退出对话"或"结束对话"），STT 转录文本匹配退出关键词
- **THEN** 系统立即退出连续聆听模式：VAD 继续运行但不触发 STT 转录，状态机回到等待唤醒词状态，推送 `conversation.ended` 事件，负载包含 `{ "reason": "user_intent", "message": "对话已结束" }`

#### Scenario: 连续聆听超阈值前静默重置计时器

- **WHEN** Chat 状态下，在 30 秒超时倒数至 15 秒时，用户再次说话触发 `voice_start`
- **THEN** 系统重置超时计时器，从 30 秒重新倒数，继续维持连续聆听模式

#### Scenario: 连续聆听模式下环形缓冲区扩展

- **WHEN** Chat 状态下用户连续多次对话（如每轮语音段长度 2-5 秒，间隔不超过 30 秒），总对话时长超过 10 秒
- **THEN** 环形缓冲区继续按 FIFO 策略覆盖旧数据，STT 每次提取的音频段仅覆盖当前 `voice_start` 到 `voice_end` 的范围（含前 1.5 秒上下文），不受历史对话数据覆盖的影响

#### Scenario: Chat 状态下短语音过滤保持不变

- **WHEN** Chat 状态下 VAD 上报 `voice_end`，但语音段持续时长 < 0.5 秒（如清嗓子、短暂环境音）
- **THEN** 系统不触发 STT 转录，不推送 `stt.transcription` 事件，超时计时器不重置，继续维持连续聆听模式

---

### Requirement: 连续聆听模式配置

系统 SHALL 在配置文件 `frank.yaml` 中提供连续聆听模式的相关配置项，包括超时时间和退出关键词列表。

#### Scenario: 自定义超时时间

- **WHEN** 用户在 `frank.yaml` 中设置 `conversation.idle_timeout` 为 60（秒）
- **THEN** 系统使用 60 秒替代默认的 30 秒超时，Chat 状态下最后一段语音结束后静默 60 秒才退出连续聆听模式

#### Scenario: 自定义退出关键词

- **WHEN** 用户在 `frank.yaml` 中设置 `conversation.exit_keywords` 为 `["退出对话", "结束对话", "就这些"]`
- **THEN** 系统在 Chat 状态下对每段 STT 转录文本进行模糊匹配，匹配任意关键词即触发连续聆听模式退出
