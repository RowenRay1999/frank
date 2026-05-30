## Context

Phase 2 完成时，Frank 已能在检测到唤醒词后进入 Chat 状态，但 Chat 状态内部是空的——没有"听懂了什么"和"如何回应"。Phase 3 构建完整的对话循环：语音→文字→理解→回复→语音。

**当前代码状态**：
- `audio_pipeline.py`: VAD + 唤醒词检测正常，环形缓冲区有完整音频，但唤醒后不做 STT
- `state_machine.py`: Chat 状态存在但只有超时回退逻辑，无对话循环
- `main.py`: 无 LLM/TTS 相关模块
- UI: 聊天面板是占位符，无消息气泡

## Goals / Non-Goals

**Goals:**
- 唤醒词 → STT 转录 → LLM 理解 → TTS 回复 → 等待下一次唤醒（完整对话闭环）
- 免唤醒指令白名单（本地匹配，不调 LLM，低延迟）
- 视觉意图检测（注视=唤醒辅助，点头/摇头=简单确认）
- 对话历史管理（保留上下文实现多轮对话）
- 流式 LLM 响应（打字机效果）+ 流式 TTS 播放

**Non-Goals:**
- 多人同时对话路由（Phase 4）
- 任务管理系统（Phase 4）
- 技能插件运行时（Phase 4）
- 情感/语气识别
- 多语言翻译（超出中文优先范围）

## Decisions

### D1: STT 使用 faster-whisper medium 模型

**决策**：faster-whisper 的 `medium` 模型（~1.5GB），CTranslate2 推理引擎，CPU 实时转写。

**替代方案**：
- A) Whisper.cpp large-v3 — 精度最高但 3GB，加载慢
- B) faster-whisper small — 轻量但中文精度损失明显

**选择**：medium 是中文精度与速度的最优平衡点。首次下载缓存到 `data/models/`，加载时间 ~5s。预期转写延迟 < 实时（1s 语音 ≈ 0.5s 转写）。

### D2: LLM 采用可插拔 Provider 架构

**决策**：定义 `LLMProvider` 抽象接口，首批实现两个 provider：
1. `OpenAIProvider` — 支持 OpenAI API 和 Azure OpenAI（通过 base_url 区分）
2. `OllamaProvider` — 本地 LLM 回退（通过 Ollama HTTP API）

用户可在配置文件中切换 provider。系统提示词自动注入当前用户身份（display_name + role）和可用技能列表。

**选择理由**：Phase 4 技能插件系统需要 LLM 做意图路由，可插拔架构允许后续无缝接入更多 LLM。本地优先原则（生物特征本地）在 LLM 层面放宽为可选——因为本地 LLM 质量参差不齐，云端 LLM 提供更好的对话体验。

### D3: TTS 使用 edge-tts（Microsoft Edge TTS 免费服务）

**决策**：`edge-tts` 库调用 Microsoft Edge 的免费 TTS 服务，中文语音自然度高。

**替代方案**：
- A) VITS 本地模型 — 完全离线但中文模型质量一般，需额外 1-2GB 模型
- B) Azure Cognitive Services TTS — 质量最高但需要 Azure 订阅

**选择**：edge-tts 免费、中文自然、无需 API Key。离线不可用时自动降级为纯文字回复。支持流式播放（SSML）。

### D4: 免唤醒指令使用本地关键词树 + 上下文校验

**决策**：预定义关键词 → 动作映射表，不经过 ASR → 不经过 LLM。每个关键词附带上下文条件（如"下一首"仅在 `media_playing=true` 时生效）。

默认白名单：
```
"暂停" / "继续" / "下一首" → media 控制（条件：is_playing=true）
"几点了" → 报时（无条件）
"大声点" / "小声点" → 音量调节（条件：is_speaking=true）
```

主人可在设置中增删条目。匹配使用 Aho-Corasick 多模式匹配算法，延迟 <5ms。

### D5: 视觉意图基于 MediaPipe Face Mesh 关键点轨迹

**决策**：复用 Phase 1/2 已有的 MediaPipe 管道。Face Mesh 提供 468 个关键点，从中提取：
- **注视检测**：左右眼中心 + 眼球位置 → 计算视线向量 → 与摄像头夹角 <10° → "正在看设备"
- **点头**：鼻尖关键点（#1）在连续帧中的 Y 轴上下移动模式 → 匹配模板
- **摇头**：鼻尖关键点在连续帧中的 X 轴左右移动模式 → 匹配模板

挥手使用 MediaPipe Hands（21 关键点），轻量级。

### D6: 对话子状态管理

Chat 状态内部分解为子状态：
```
Chat
├── Listening    (等待语音输入，显示波形)
├── Transcribing (STT 转写中，显示"...")
├── Thinking     (LLM 推理中，显示加载动画)
└── Speaking     (TTS 播放中，显示音量指示)
```

子状态驱动 UI 动画和输入状态提示，用户始终知道 Frank 在做什么。

## Risks / Trade-offs

- **[R1] faster-whisper 首次加载慢（5-10s）** → 后台异步加载，加载期间唤醒词检测正常工作，STT 就绪前语音输入排队等待
- **[R2] 云端 LLM 网络延迟** → 超时 15s，超时后自动回退 Ollama 本地 LLM；UI 显示"网络较慢，正在切换到本地模型..."
- **[R3] edge-tts 服务不可用** → 纯文字回复降级，不阻塞对话。重试 2 次后退化为 text-only 模式
- **[R4] 免唤醒误触发** → 上下文条件校验 + 人脸方向二次确认；安静环境中电视声说"暂停"不会触发
- **[R5] LLM API Key 安全** → 通过环境变量 `FRANK_LLM_API_KEY` 或系统凭据管理器存储，不写入 YAML 配置文件
