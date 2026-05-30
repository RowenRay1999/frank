## Why

Phase 1 让 Frank 能"看到人、听到声"，Phase 2 让 Frank 能"认出谁是谁"。但 Frank 还不会"听懂话"和"回答"。用户说"Hey Frank"唤醒后，系统进入 Chat 状态却什么也不发生——没有语音转文字、没有语义理解、没有语音回复。Phase 3 填补从"感知"到"对话"的关键缺口：把语音变成文字、用 AI 理解意图、用语音或文字回复用户。这是 Frank 从"识别器"变成"助手"的质变。

## What Changes

- 集成本地语音转文字（faster-whisper）：唤醒词命中后从环形缓冲区提取语音段 → STT 转录为中文文本
- 集成云端大语言模型（Azure OpenAI / OpenAI API，可选 Ollama 本地回退）：接收转录文本 + 身份上下文 + 角色权限 → 生成回复
- 集成文字转语音（edge-tts，免费中文 TTS）：LLM 回复 → 语音朗读，通过系统音频设备播放
- 实现免唤醒指令：高频命令白名单（"几点了"/"暂停"/"下一首"/"大声点"等），本地关键词匹配，不经过 LLM
- 实现视觉意图识别：基于 MediaPipe Face Mesh（468 关键点）检测注视方向、点头/摇头手势
- 完善交互反馈链：声音🔊→唤醒词🎯→转写📝→理解💡→回复💬，每步状态可见
- 对话历史管理：保留最近 N 轮对话上下文，支持多轮对话

## Capabilities

### New Capabilities
- `speech-to-text`: 本地语音转文字管线——faster-whisper 模型集成、环形缓冲区音频提取、多语言支持（中文优先）、转录文本推送
- `llm-integration`: 云端 LLM 对话引擎——Azure OpenAI / OpenAI API 调用、身份+角色上下文注入、对话历史管理、Ollama 本地回退、流式响应支持
- `text-to-speech`: 文字转语音输出——edge-tts 中文语音合成、系统音频设备播放、可配置语速/音色、流式播放
- `wake-free-commands`: 免唤醒指令系统——白名单定义与管理、本地关键词匹配、上下文校验（如仅媒体播放时"下一首"生效）、主人可管理白名单
- `visual-intent`: 视觉意图识别——MediaPipe Face Mesh 注视检测（看向设备>2s → 唤醒）、点头/摇头识别（确认/否认问题）、挥手唤醒

### Modified Capabilities
- `audio-pipeline`: 唤醒词命中后触发 STT 处理链——从环形缓冲区截取音频段 → 送 faster-whisper 转写 → 推送转录结果
- `state-machine`: Chat 状态新增对话循环——STT→LLM→TTS→等待下一次唤醒/指令；新增 Listening/Thinking/Speaking 子状态
- `ui-shell`: 对话面板从占位升级为真实聊天界面——用户消息气泡、助手回复气泡（文字+语音播放指示）、子状态动画、免唤醒指令反馈

## Impact

- **新增依赖**：faster-whisper、edge-tts、openai（或 azure-ai-inference）
- **新增文件**：`src/python/modules/stt/`、`src/python/modules/llm/`、`src/python/modules/tts/`、`src/python/modules/wakefree/`、`src/python/modules/visual_intent/`
- **修改文件**：audio_pipeline.py（STT 链）、state_machine.py（子状态）、main.py（新模块注册）、renderer/*（对话 UI）
- **配置新增**：`config/frank.yaml` 中 llm（provider/model/api_key）、tts（voice/speed）、wakefree（commands 列表）、visual_intent（gaze_threshold/nod_threshold）
- **无破坏性变更**：所有 Phase 1/2 接口保持向后兼容
