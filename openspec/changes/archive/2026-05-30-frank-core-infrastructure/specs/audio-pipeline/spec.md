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
Python 推理服务 SHALL 使用 OpenWakeWord 模型持续对音频流进行唤醒词检测。默认唤醒词为 "Hey Frank"，可在配置文件 `frank.yaml` 的 `wake_word.text` 中自定义。检测到唤醒词时 SHALL 向 Electron 推送 `mic.wake_word` 事件。

#### Scenario: 标准唤醒词检测
- **WHEN** 用户说出 "Hey Frank"，OpenWakeWord 模型输出的置信度分数超过阈值 0.7
- **THEN** Python 向 Electron 推送 `mic.wake_word` 事件，负载包含 `{ "confidence": 0.85, "timestamp": <采集时间戳> }`，同时触发状态机转换到 Chat 状态

#### Scenario: 低置信度唤醒不触发
- **WHEN** 模型输出的置信度分数为 0.55，低于阈值 0.7
- **THEN** 不产生 `mic.wake_word` 事件，麦克风继续监听，状态机保持在当前状态

#### Scenario: 唤醒词置信度与面部检测联合校验（防误触）
- **WHEN** OpenWakeWord 检测到唤醒词且置信度 >= 0.7
- **THEN** 唤醒词事件仅在满足以下任一条件时才被视为有效：a) 摄像头在同一时刻检测到人脸且朝向设备，或 b) 唤醒词触发前后 1 秒窗口内有面部检测记录；否则事件被降级，不触发状态转换

#### Scenario: 自定义唤醒词
- **WHEN** 用户在配置文件中将 `wake_word.text` 修改为 "Hey Frankie"，同时提供了自定义 OpenWakeWord 模型文件 `wake_word.model_path`
- **THEN** Python 服务加载指定模型并以新唤醒词进行检测，其余行为与默认唤醒词一致

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
