## ADDED Requirements

### Requirement: 麦克风设备枚举
Python 推理服务在启动时以及运行期间 SHALL 通过 PyAudio 枚举系统上所有可用的音频输入设备，并将设备信息上报给 Electron 主进程。

#### Scenario: 启动时枚举所有音频输入设备
- **WHEN** Python 推理服务启动，调用 PyAudio 的 `pyaudio.PyAudio().get_host_api_info_by_index()` 和 `get_device_info_by_host_api_device_index()` 遍历所有音频输入设备
- **THEN** 服务端生成设备列表并推送 `mic.devices` 事件到 Electron，列表包含如下结构的条目：`{ "id": 0, "name": "Microphone (Realtek Audio)", "sample_rates": [8000, 16000, 44100, 48000], "channels": 2, "default": true }`

#### Scenario: 默认设备由配置决定
- **WHEN** 配置 `frank.yaml` 中指定了 `mic.device_id` 为特定值，且该设备在系统中存在
- **THEN** Python 将该设备标记为默认设备，在 `mic.devices` 事件中对应条目的 `default` 字段为 `true`

#### Scenario: 设备热插拔响应
- **WHEN** 运行期间有新麦克风插入或现有麦克风拔出
- **THEN** Python 服务在检测到设备列表变化后，重新枚举并推送更新的 `mic.devices` 事件到 Electron

---

### Requirement: 音频采集
Python 推理服务 SHALL 以 16kHz 采样率、16-bit 位深、单声道 PCM 格式从麦克风采集音频，在 PyAudio 回调模式下以 512 样本（约 32ms）为 chunk 大小持续读取音频数据。

#### Scenario: 标准音频采集并分块推送
- **WHEN** 麦克风已启动且 PyAudio 流处于活动状态，每采集到 512 个 16-bit PCM 样本
- **THEN** 音频数据以 `numpy.ndarray` 格式（dtype=int16, shape=(512,)）写入环形缓冲区，并送入 VAD 和唤醒词检测模块

#### Scenario: 噪声抑制与自动增益控制
- **WHEN** 音频预处理阶段启用了 `audio.noise_suppression` 配置项
- **THEN** Python 服务使用 RNNoise 对每个音频 chunk 进行噪声抑制处理，降低环境噪音后再送入环形缓冲区；同时自动增益控制（AGC）将 RMS 电平归一化到目标 -26 dBFS

#### Scenario: 噪声抑制关闭时原始直通
- **WHEN** 配置中 `audio.noise_suppression` 为 `false`
- **THEN** Python 服务跳过噪声抑制和 AGC 处理，原始 PCM 数据直接写入环形缓冲区

---

### Requirement: 环形缓冲区
Python 推理服务 SHALL 维护一个 10 秒容量的线程安全环形缓冲区，以 16kHz、16-bit 单声道 PCM 格式持续存储最近的音频样本。当唤醒词或 VAD 触发时，缓冲区 SHALL 提取从触发位置前 1.5 秒开始直至检测到静默结束的音频段。

#### Scenario: 唤醒词触发后提取音频段
- **WHEN** OpenWakeWord 检测到唤醒词，触发位置为 `trigger_pos`（时间戳刻度），且缓冲区中有 10 秒可用数据
- **THEN** 提取从 `trigger_pos - 24000 样本（1.5秒）` 开始到 `trigger_pos` 之后 VAD 检测到连续 0.5 秒静默为止的完整音频段，作为 `numpy.ndarray` 传递给下游处理（Phase 3 中的 STT）

#### Scenario: VAD 触发后提取语音段
- **WHEN** VAD 上报 `voice_start` 事件（语音开始），随后 VAD 上报 `voice_end` 事件（语音结束）
- **THEN** 环形缓冲区提取从 `voice_start - 24000 样本（1.5秒）` 到 `voice_end` 位置的音频段，用于后续分析或保存

#### Scenario: 线程安全并发读写
- **WHEN** 音频采集线程以 512 样本为 chunk 持续写入缓冲区，同时 VAD 检测线程在另一个协程中触发读取操作
- **THEN** 读写操作互不阻塞，读取获取到的数据始终是某一时刻的完整快照，不存在数据竞争或撕裂

#### Scenario: 缓冲区到达容量上限时覆盖旧数据
- **WHEN** 环形缓冲区已存满 160000 样本（10秒 @ 16kHz）且新音频继续写入
- **THEN** 最早的样本被覆盖，缓冲区始终保持最近的 10 秒数据

---

### Requirement: 语音活动检测（VAD）
Python 推理服务 SHALL 使用 Silero VAD 模型对每个音频 chunk 进行语音活动检测。VAD 输出 `speech_probability`（0-1 浮点数），阈值默认为 0.5。VAD 状态变化时 SHALL 向 Electron 推送 `mic.voice_start` 和 `mic.voice_end` 事件。

#### Scenario: 语音开始检测
- **WHEN** 连续音频 chunk 的 `speech_probability` 从低于 0.5 变为高于 0.5
- **THEN** Python 立即向 Electron 推送 `mic.voice_start` 事件，包含 `{ "probability": <当前概率> }` 负载

#### Scenario: 语音结束检测
- **WHEN** `speech_probability` 连续低于 0.5 且持续时间达到 0.5 秒（约 16 个 audio chunk）
- **THEN** Python 向 Electron 推送 `mic.voice_end` 事件，包含 `{ "probability": <当前概率>, "duration": <语音段时长秒> }` 负载

#### Scenario: 短时概率抖动不触发误报
- **WHEN** `speech_probability` 在临界值 0.5 附近短暂上下波动（单次或两次 chunk 在 0.4-0.6 之间振荡）
- **THEN** VAD 模块的滞回逻辑抑制这些短暂抖动，不触发 `voice_end`；等待连续低于阈值达 0.5 秒后才判定语音结束

#### Scenario: VAD 在静音环境下保持沉默
- **WHEN** 环境安静，`speech_probability` 持续低于 0.5
- **THEN** 不产生任何 `voice_start` 或 `voice_end` 事件，事件推送频率为零

---

### Requirement: 唤醒词检测

Python 推理服务 SHALL 使用 OpenWakeWord 模型持续对音频流进行唤醒词检测。默认唤醒词为 "Hey Frank"，可在配置文件 `frank.yaml` 的 `wake_word.text` 中自定义。检测到唤醒词时 SHALL 向 Electron 推送 `mic.wake_word` 事件。当唤醒词所在的语音段长度满足最低要求（>= 1.5 秒）且质量检测通过时，事件负载中 SHALL 可选包含 `voiceprint_embedding` 字段，值为 192 维声纹嵌入向量。

#### Scenario: 标准唤醒词检测

- **WHEN** 用户说出 "Hey Frank"，OpenWakeWord 模型输出的置信度分数超过阈值 0.7
- **THEN** Python 向 Electron 推送 `mic.wake_word` 事件。若唤醒词所在语音段同时满足声纹提取条件（时长 >= 1.5 秒，SNR > 10dB，单说话人），则负载包含 `{ "confidence": 0.85, "timestamp": <采集时间戳>, "voiceprint_embedding": [192 维浮点数组], "voiceprint_duration": <语音段时长秒> }`；若不满足条件，则负载保持原有格式 `{ "confidence": 0.85, "timestamp": <采集时间戳> }`。事件推送后**SHALL 启动 STT 处理链**：从环形缓冲区提取 `trigger_pos - 24000 样本（1.5秒）` 开始到 VAD 检测到连续 0.5 秒静默为止的完整音频段，送入 STT 模块进行转录

#### Scenario: 低置信度唤醒不触发

- **WHEN** 模型输出的置信度分数为 0.55，低于阈值 0.7
- **THEN** 不产生 `mic.wake_word` 事件，麦克风继续监听，状态机保持在当前状态

#### Scenario: 唤醒词置信度与面部检测联合校验（防误触）

- **WHEN** OpenWakeWord 检测到唤醒词且置信度 >= 0.7
- **THEN** 唤醒词事件仅在满足以下任一条件时才被视为有效：a) 摄像头在同一时刻检测到人脸且朝向设备，或 b) 唤醒词触发前后 1 秒窗口内有面部检测记录；否则事件被降级，不触发状态转换。声纹嵌入提取不受联合校验结果影响——即使事件被降级，若语音段满足条件仍会执行声纹提取并缓存嵌入供后续使用

#### Scenario: 自定义唤醒词

- **WHEN** 用户在配置文件中将 `wake_word.text` 修改为 "Hey Frankie"，同时提供了自定义 OpenWakeWord 模型文件 `wake_word.model_path`
- **THEN** Python 服务加载指定模型并以新唤醒词进行检测，声纹嵌入提取逻辑与默认唤醒词一致

---

### Requirement: 麦克风启动与停止
Electron 主进程 SHALL 通过 WebSocket 发送 `mic.start` 和 `mic.stop` 控制指令。Python 推理服务收到 `mic.start` 后 SHALL 初始化麦克风设备、加载 VAD 和唤醒词模型并启动采集循环。收到 `mic.stop` 后 SHALL 关闭音频流并卸载相关资源。

#### Scenario: 正常启动流程
- **WHEN** Electron 发送 `{ "type": "mic.start", "device_id": 0 }`
- **THEN** Python 打开指定麦克风的 PyAudio 流（若 `device_id` 未指定则使用默认设备），加载 Silero VAD 模型和 OpenWakeWord 模型，启动音频采集循环，并向 Electron 回复 `{ "type": "mic.started", "device": { "id": 0, "name": "..." } }`

#### Scenario: 正常停止流程
- **WHEN** Electron 发送 `{ "type": "mic.stop" }`
- **THEN** Python 停止 PyAudio 流、关闭回调、释放模型资源（卸载 VAD 和唤醒词），向 Electron 回复 `{ "type": "mic.stopped" }`

#### Scenario: 应用退出自动停止
- **WHEN** 用户关闭 Frank 应用，Electron 主进程退出前发送 `shutdown` 信号到 Python
- **THEN** Python 检测到 shutdown 信号，自动执行 mic.stop 流程关闭麦克风，释放所有音频资源

#### Scenario: 同一设备重复启动不产生新流
- **WHEN** Electron 在已收到 `mic.started` 回调后再次发送 `mic.start`
- **THEN** Python 忽略重复的 start 指令，回复 `{ "type": "mic.started", "already_active": true }`

---

### Requirement: 错误处理
Python 推理服务在麦克风操作过程中遇到错误时 SHALL 向 Electron 推送 `mic.error` 事件，包含错误码、可恢复标志和建议操作。

#### Scenario: 麦克风未找到
- **WHEN** Electron 发送 `mic.start` 时指定的 `device_id` 在系统设备列表中不存在，或系统完全无音频输入设备
- **THEN** Python 回复 `{ "type": "mic.error", "code": "MIC_NOT_FOUND", "recoverable": true, "suggestion": "请检查麦克风是否已连接并安装驱动，或尝试其他设备" }`，Electron 在 UI 显示设备不可用提示

#### Scenario: 权限被拒绝
- **WHEN** PyAudio 调用 `stream.open()` 时抛出 `OSError` 或 `IOError`，原因是 Windows 麦克风权限被禁用
- **THEN** Python 回复 `{ "type": "mic.error", "code": "MIC_PERMISSION_DENIED", "recoverable": true, "suggestion": "请在 Windows 设置 > 隐私和安全性 > 麦克风中允许 Frank 访问麦克风" }`，Electron 打开系统隐私设置引导链接

#### Scenario: 运行中麦克风断开
- **WHEN** 在音频采集循环中，PyAudio 回调抛出设备断开相关异常（如 `PortAudioError` -9996）
- **THEN** Python 立即停止当前流，推送 `{ "type": "mic.error", "code": "MIC_DISCONNECTED", "recoverable": true, "suggestion": "麦克风已断开连接，请重新插拔后再次启动" }`，自动尝试在设备重新出现后恢复采集

#### Scenario: 模型加载失败
- **WHEN** VAD 或 OpenWakeWord 模型文件不存在、损坏或版本不兼容导致加载异常
- **THEN** Python 回复 `{ "type": "mic.error", "code": "MODEL_LOAD_FAILED", "recoverable": false, "suggestion": "模型文件缺失或损坏，请重新安装或更新应用" }`，服务进入降级运行状态（仅传递原始音频流而不进行检测）

---

### Requirement: 性能指标
音频管道各个阶段 SHALL 满足以下延迟目标：VAD 处理延迟 < 10ms 每 chunk，唤醒词检测延迟 < 100ms（从单词结束到事件发出），端到端管道延迟（音频进入事件出）< 150ms。

#### Scenario: VAD 处理满足延迟目标
- **WHEN** 音频采集线程将 512 样本 chunk 送入 Silero VAD 模型
- **THEN** VAD 推理从输入到返回 `speech_probability` 的耗时不超过 10ms（在 Python 3.11+、CPU 支持 AVX2 的条件下）

#### Scenario: 唤醒词检测满足延迟目标
- **WHEN** 用户说完 "Hey Frank" 的最后一个音节
- **THEN** OpenWakeWord 模型在 100ms 内完成检测并生成 `mic.wake_word` 事件推送

#### Scenario: 端到端管道延迟
- **WHEN** 音频从麦克风进入 PyAudio 回调函数
- **THEN** 经 chunk 拼接、VAD 推理、唤醒词模型推理后，事件（`voice_start` / `voice_end` / `wake_word`）在 150ms 内推送至 Electron 端

#### Scenario: 高负载下延迟不退化
- **WHEN** CPU 在运行人脸检测等其他任务，系统整体负载达到 80%
- **THEN** VAD 延迟仍保持在 15ms 以内，唤醒词检测延迟保持在 120ms 以内，不出现明显的检测事件滞后于用户语音的现象

---

### Requirement: 声纹嵌入提取

当 Silero VAD 检测到语音开始（`voice_start`）时，Python 推理服务 SHALL 开始缓冲音频数据。当 VAD 上报语音结束（`voice_end`）时，服务 SHALL 从环形缓冲区提取完整的语音段，并对其运行 SpeechBrain ECAPA-TDNN 模型，提取 192 维说话人嵌入向量。提取成功后，服务 SHALL 向 Electron 推送 `mic.voiceprint` 事件，包含嵌入向量及对应的时间戳。

#### Scenario: 语音段完成后提取声纹嵌入

- **WHEN** VAD 上报 `voice_end` 事件，且从缓冲区提取的完整语音段持续时间 >= 1.5 秒，且满足音频质量条件（SNR > 10dB、单说话人）
- **THEN** 系统将完整语音段输入 SpeechBrain ECAPA-TDNN 模型，输出 192 维 L2 归一化浮点嵌入向量，并推送 `mic.voiceprint` 事件，负载包含 `{ "embedding": [192 维浮点数组], "timestamp": <语音段开始时间戳>, "duration": <语音段时长秒> }`

#### Scenario: 语音段长度不足不提取嵌入

- **WHEN** VAD 上报 `voice_end` 事件，但语音段持续时间 < 1.5 秒
- **THEN** 系统跳过 ECAPA-TDNN 推理，不产生 `mic.voiceprint` 事件，仅保留原有的 VAD 事件

#### Scenario: 声纹模型推理失败

- **WHEN** SpeechBrain ECAPA-TDNN 模型推理抛出异常（如输入张量形状不匹配、模型加载异常）
- **THEN** 系统推送 `mic.error` 事件，`code` 为 `"VOICEPRINT_EXTRACTION_FAILED"`，`recoverable` 为 `true`，suggestion 为 `"声纹嵌入提取失败，该语音段将跳过声纹识别"`，不影响后续语音段的处理

---

### Requirement: 声纹提取最低语音时长

系统 SHALL 仅对持续时间 >= 1.5 秒的连续语音段进行声纹嵌入提取。短于该阈值的语音段仅产生 VAD 事件，不触发 ECAPA-TDNN 推理。

#### Scenario: 超长语音段正常提取

- **WHEN** 用户连续说话 3.2 秒，VAD 检测到 `voice_start` 到 `voice_end` 间隔为 3.2 秒
- **THEN** 系统将 3.2 秒语音段送入 ECAPA-TDNN，提取 192 维嵌入，推送 `mic.voiceprint` 事件

#### Scenario: 短语音段跳过声纹

- **WHEN** 用户只说"嗯"或"好"，语音段仅 0.8 秒
- **THEN** 系统不运行 ECAPA-TDNN 模型，不产生 `mic.voiceprint` 事件，仅推送标准的 `voice_end` 事件

#### Scenario: 阈值可配置

- **WHEN** 用户在配置文件中将 `voiceprint.min_duration` 设置为 2.0（秒）
- **THEN** 系统使用配置值替代默认的 1.5 秒阈值，仅对 >= 2.0 秒的语音段提取声纹嵌入

---

### Requirement: 声纹质量检测

系统 SHALL 在运行 ECAPA-TDNN 模型前对语音段进行质量检测，仅当同时满足以下条件时才执行声纹嵌入提取：估计信噪比（SNR）> 10dB，且语音段包含且仅包含单一说话人（无重叠语音）。

#### Scenario: SNR 达标且单说话人

- **WHEN** 语音段估计 SNR 为 18dB，且 VAD 期间无检测到多说话人特征
- **THEN** 系统判定质量达标，执行 ECAPA-TDNN 推理并提取嵌入

#### Scenario: 背景噪声过大

- **WHEN** 语音段估计 SNR 为 5dB（环境嘈杂，如吸尘器运行中）
- **THEN** 系统判定质量不达标，跳过声纹提取，不产生 `mic.voiceprint` 事件

#### Scenario: 多人同时说话

- **WHEN** 语音段中发现存在两路及以上活动声源（基于频谱交叉分析或能量分布多峰判定）
- **THEN** 系统判定包含重叠语音，跳过声纹提取，不产生 `mic.voiceprint` 事件

#### Scenario: SNR 估计方法

- **WHEN** 语音段已提取完毕等待质量检测
- **THEN** 系统使用语音段前 200ms（无声段）估计噪声本底能量，与整个语音段平均能量的比值计算 SNR（dB = 20 * log10(rms_voice / rms_noise)）。若 SNR <= 10dB，标记为不合格

---

### Requirement: 唤醒词联动声纹嵌入

当 OpenWakeWord 检测到唤醒词时，系统 SHALL 同时触发声纹嵌入提取，使用环形缓冲区获取唤醒词触发时刻前 1.5 秒开始至 VAD 检测到连续 0.5 秒静默为止的完整语音段，对该段运行 ECAPA-TDNN 模型。若语音段满足最低时长（>= 1.5 秒）和质量条件，声纹嵌入 SHALL 作为 `voiceprint_embedding` 字段附加到唤醒词事件负载中。

#### Scenario: 唤醒词 + 声纹嵌入同时产出

- **WHEN** 用户说"Hey Frank [指令内容]"，总语音时长 2.5 秒，质量检测通过
- **THEN** 系统同时在唤醒词检测线程和声纹提取线程运行，最终 `mic.wake_word` 事件负载包含 `{ "confidence": 0.85, "timestamp": <时间戳>, "voiceprint_embedding": [192 维浮点数组], "voiceprint_duration": 2.5 }`

#### Scenario: 唤醒词语音段过短无声纹

- **WHEN** 用户只说"Hey Frank"（约 0.8 秒），语音段不足 1.5 秒
- **THEN** 系统跳过声纹提取，`mic.wake_word` 事件负载中 `voiceprint_embedding` 字段为 `null`，保持原有格式 `{ "confidence": 0.85, "timestamp": <时间戳> }`

#### Scenario: 唤醒词语音段质量不达标无声纹

- **WHEN** 用户说"Hey Frank [指令内容]"，语音段 2.0 秒但 SNR 不足 10dB
- **THEN** 系统跳过声纹提取，`mic.wake_word` 事件负载中 `voiceprint_embedding` 字段为 `null`，保持原有格式 `{ "confidence": 0.85, "timestamp": <时间戳> }`

#### Scenario: 环形缓冲区提供唤醒词前的语音上下文

- **WHEN** OpenWakeWord 在位置 `trigger_pos` 检测到唤醒词
- **THEN** 系统从环形缓冲区提取从 `trigger_pos - 24000 样本（1.5秒）` 开始到 `trigger_pos` 之后 VAD 检测到连续 0.5 秒静默为止的完整语音段，确保唤醒词前后的语音内容完整保留以用于声纹提取

---

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
