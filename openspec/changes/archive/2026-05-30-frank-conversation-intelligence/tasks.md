## 1. 依赖安装与配置

- [x] 1.1 安装 faster-whisper + CTranslate2，模型首次运行时下载 medium 模型到 `data/models/`
- [x] 1.2 安装 edge-tts 库
- [x] 1.3 安装 openai SDK（用于 OpenAI / Azure OpenAI 调用）
- [x] 1.4 更新 `config/frank.yaml`：新增 llm、tts、wakefree、visual_intent 配置段
- [x] 1.5 更新 `src/python/requirements.txt`：添加 faster-whisper, edge-tts, openai

## 2. 语音转文字（STT）

- [x] 2.1 创建 `src/python/modules/stt/` 模块：faster-whisper 模型加载（异步，启动时后台加载）、转录接口
- [x] 2.2 实现音频段提取：唤醒词命中后从环形缓冲区截取 [触发点-1.5s, 触发点+至静音] 音频段，重采样为 16kHz mono
- [x] 2.3 实现 STT 转录：faster-whisper transcribe，language=zh，beam_size=5，返回文本+置信度
- [x] 2.4 推送 `stt.transcription` 事件到 Electron：{ text, confidence, duration_ms, language }
- [x] 2.5 实现 Chat 状态持续监听：第一次转录后保持 VAD 活跃，voice_end → 自动转录无需重新唤醒词

## 3. 云端 LLM 集成

- [x] 3.1 创建 `src/python/modules/llm/` 模块：定义 LLMProvider 抽象基类（async generate(prompt, context) → response）
- [x] 3.2 实现 OpenAIProvider：支持 OpenAI API 和 Azure OpenAI（通过 base_url 区分），读取 FRANK_LLM_API_KEY 环境变量
- [x] 3.3 实现 OllamaProvider：本地 LLM 回退（http://localhost:11434 API）
- [x] 3.4 实现系统提示词注入：自动拼接身份上下文（display_name, role）+ 可用能力 + 对话规范
- [x] 3.5 实现对话历史管理：保留最近 10 轮，超 token 预算时裁剪最旧消息
- [x] 3.6 实现流式响应：SSE → "llm.token" 事件逐 token 推送 → 完成时 "llm.response"
- [x] 3.7 实现 Provider 自动回退：15s 超时或错误 → Ollama → 两者都失败返回离线回复

## 4. 文字转语音（TTS）

- [x] 4.1 创建 `src/python/modules/tts/` 模块：edge-tts 集成，默认 zh-CN-XiaoxiaoNeural 语音
- [x] 4.2 实现 TTS 合成：LLM 回复文本 → MP3 流 → 系统默认音频设备播放
- [x] 4.3 实现流式播放：边下载边播放，减少首字延迟
- [x] 4.4 推送 TTS 事件：tts.start / tts.progress / tts.complete
- [x] 4.5 实现 TTS 中断：VAD 检测到 voice_start 时立即停止播放，切回 Listening
- [x] 4.6 实现 TTS 降级：edge-tts 失败重试 2 次 → text-only 模式 + tts.unavailable 事件

## 5. 免唤醒指令

- [x] 5.1 创建 `src/python/modules/wakefree/` 模块：定义白名单数据结构 { keyword, action, condition }
- [x] 5.2 实现 Aho-Corasick 多模式匹配：编译关键词 → trie，O(n) 匹配，<5ms 延迟
- [x] 5.3 实现内置白名单：几点了(time)、暂停/继续/下一首(media,条件)、大声点/小声点(volume,条件)
- [x] 5.4 实现条件校验：执行前检查上下文条件 + 人脸存在（2s 内检测到）
- [x] 5.5 实现主人白名单管理：add/remove/list，配置持久化到 config
- [x] 5.6 实现免唤醒反馈：简短 UI 提示 + 可选短音效

## 6. 视觉意图识别

- [x] 6.1 创建 `src/python/modules/visual_intent/` 模块：基于 MediaPipe Face Mesh（468 关键点）
- [x] 6.2 实现注视检测：眼心+眼球位置→视线向量→与摄像头夹角<10°持续>2s → visual.gaze_detected
- [x] 6.3 实现点头检测：鼻尖 Y 轴位移模式匹配（1s 窗口）→ visual.nod
- [x] 6.4 实现摇头检测：鼻尖 X 轴位移模式匹配（1s 窗口）→ visual.shake
- [x] 6.5 实现挥手检测：MediaPipe Hands 21 关键点 → 手掌横向移动 > 阈值 → visual.wave
- [x] 6.6 视觉事件接入触发融合逻辑：gaze + voice → 绕过唤醒词直达 STT；nod/shake → 确认/否认问题

## 7. 核心模块集成

- [x] 7.1 更新 `audio_pipeline.py`：唤醒词命中后触发 STT 处理链
- [x] 7.2 更新 `state_machine.py`：Chat 状态新增 Listening/Transcribing/Thinking/Speaking 子状态 + 对话循环
- [x] 7.3 更新 `main.py`：注册 stt/llm/tts/wakefree/visual_intent 模块，接线回调，新增消息类型
- [x] 7.4 实现对话编排器：协调 STT→LLM→TTS 流水线，管理子状态转换
- [x] 7.5 更新 `main.js`：新增 stt.*、llm.*、tts.*、wakefree.*、visual.* 消息路由

## 8. UI 升级

- [x] 8.1 升级聊天面板：用户消息气泡（右对齐，转录文本）+ 助手消息气泡（左对齐，LLM 回复 + TTS 播放按钮）
- [x] 8.2 实现子状态动画：Listening=波形、Transcribing=省略号脉动、Thinking=旋转加载、Speaking=音量条
- [x] 8.3 实现 TTS 控制：播放/暂停/重播按钮，音量滑块
- [x] 8.4 实现免唤醒反馈：简短 toast 通知
- [x] 8.5 更新 preload.js：新增 stt/llm/tts/wakefree/visual 事件监听
- [x] 8.6 更新 styles.css：消息气泡样式、子状态动画、TTS 控件样式

## 9. 集成验证

- [ ] 9.1 STT 端到端测试：说"Hey Frank 今天天气怎么样" → 唤醒词命中 → STT 转录正确 → 文本推送到 UI
- [ ] 9.2 LLM 对话测试：LLM 收到"今天天气怎么样" → 返回天气回复 → UI 显示回复文本
- [ ] 9.3 TTS 播放测试：LLM 回复 → TTS 朗读 → 音频播放正常
- [ ] 9.4 免唤醒指令测试：说"几点了"（无需唤醒词）→ 系统报时
- [ ] 9.5 注视检测测试：盯住摄像头 2 秒 → visual.gaze_detected 事件 → 状态机 Aware
- [ ] 9.6 多轮对话测试：连续 3 轮对话 → 上下文保持 → 回复相关
- [ ] 9.7 降级测试：断开网络 → LLM 回退 Ollama → TTS 降级 text-only
