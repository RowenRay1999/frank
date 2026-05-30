# Audio Pipeline 音频流水线

## ADDED Requirements

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

## MODIFIED Requirements

### Requirement: 唤醒词检测

Python 推理服务 SHALL 使用 OpenWakeWord 模型持续对音频流进行唤醒词检测。默认唤醒词为 "Hey Frank"，可在配置文件 `frank.yaml` 的 `wake_word.text` 中自定义。检测到唤醒词时 SHALL 向 Electron 推送 `mic.wake_word` 事件。当唤醒词所在的语音段长度满足最低要求（>= 1.5 秒）且质量检测通过时，事件负载中 SHALL 可选包含 `voiceprint_embedding` 字段，值为 192 维声纹嵌入向量。

#### Scenario: 标准唤醒词检测

- **WHEN** 用户说出 "Hey Frank"，OpenWakeWord 模型输出的置信度分数超过阈值 0.7
- **THEN** Python 向 Electron 推送 `mic.wake_word` 事件。若唤醒词所在语音段同时满足声纹提取条件（时长 >= 1.5 秒，SNR > 10dB，单说话人），则负载包含 `{ "confidence": 0.85, "timestamp": <采集时间戳>, "voiceprint_embedding": [192 维浮点数组], "voiceprint_duration": <语音段时长秒> }`；若不满足条件，则负载保持原有格式 `{ "confidence": 0.85, "timestamp": <采集时间戳> }`。事件推送同时触发状态机转换到 Chat 状态

#### Scenario: 低置信度唤醒不触发

- **WHEN** 模型输出的置信度分数为 0.55，低于阈值 0.7
- **THEN** 不产生 `mic.wake_word` 事件，麦克风继续监听，状态机保持在当前状态

#### Scenario: 唤醒词置信度与面部检测联合校验（防误触）

- **WHEN** OpenWakeWord 检测到唤醒词且置信度 >= 0.7
- **THEN** 唤醒词事件仅在满足以下任一条件时才被视为有效：a) 摄像头在同一时刻检测到人脸且朝向设备，或 b) 唤醒词触发前后 1 秒窗口内有面部检测记录；否则事件被降级，不触发状态转换。声纹嵌入提取不受联合校验结果影响——即使事件被降级，若语音段满足条件仍会执行声纹提取并缓存嵌入供后续使用

#### Scenario: 自定义唤醒词

- **WHEN** 用户在配置文件中将 `wake_word.text` 修改为 "Hey Frankie"，同时提供了自定义 OpenWakeWord 模型文件 `wake_word.model_path`
- **THEN** Python 服务加载指定模型并以新唤醒词进行检测，声纹嵌入提取逻辑与默认唤醒词一致
