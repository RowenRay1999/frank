## Why

Frank 项目初始化的代码评审发现 15 个缺陷（6 个 CRITICAL、5 个 HIGH、4 个 MEDIUM），涉及音频、TTS、技能、对话、身份融合、手势识别等核心模块。其中 TTS 播放、技能执行、对话事件广播等关键用户路径完全失效，阻塞项目进入功能验证阶段。本次变更在进入下一开发周期前集中修复所有已确认缺陷。

## What Changes

**P0 CRITICAL — 阻塞核心用户场景的 6 个缺陷：**
- 修复 TTS 在 Windows 上使用 `winsound` 无法播放 MP3 的问题，改用 `pygame` 或 `playsound`
- 修复技能加载器在 Windows spawn 模式下因嵌套函数无法 pickle 导致所有技能崩溃
- 修复 ConversationOrchestrator 中 5 处 async 回调调用缺失 `await`，导致对话消息永远不广播到 Electron
- 修复 AudioPipeline 后台线程中 `asyncio.get_event_loop()` 在 Python 3.10+ 抛出 RuntimeError，导致语音/唤醒词/声纹事件全部丢失
- 修复 Electron 托盘"退出"菜单在 Windows 上只隐藏窗口不退出进程
- 修复 OllamaProvider 流式响应将 TCP 原始字节块当完整 JSON 行解析，导致随机 token 丢失

**P1 HIGH — 功能受损或安全旁路的 5 个缺陷：**
- 连接 STT/LLM/TTS 模块的 8 个回调到 broadcast_event，恢复流式 token 和转写结果广播
- 修复 IdentityFusionEngine 的 `_check_auto_discovery` 从未被调用，启用陌生人自动发现
- 添加技能执行时的 `min_user_level` 权限校验，修复授权绕过
- 将 CameraPipeline 中 `import mediapipe` 从模块顶层改为延迟导入，避免依赖缺失时服务器崩溃
- 修复 StateMachine 中唤醒词仅在 Auth/Chat 状态处理的问题，扩展为所有状态

**P2 MEDIUM — 体验和资源问题的 4 个缺陷：**
- 修复走近手势使用 MediaPipe 相对 Z 坐标导致无法检测，改用 bbox 面积变化
- 修复 `on_pose_frame` 中对 raise_hand 手势的冗余第二次调用导致事件重复
- 修复 LLMManager.chat() 流式成功时 `_on_response` 回调被触发两次
- 修复 TTS 临时 MP3 文件播放后未删除，累积泄露磁盘空间

## Capabilities

### New Capabilities

无。本次为纯缺陷修复，不引入新能力。

### Modified Capabilities

- `skill-plugin-system`: 新增技能执行时的角色权限校验（`min_user_level` 字段必须生效）
- `state-machine`: 唤醒词处理扩展为接受所有状态（Idle/Aware/Auth/Chat），而非仅 Auth/Chat
- `identity-fusion`: 身份融合引擎启用自动发现未标识访客功能（`_check_auto_discovery` 接入主循环）

## Impact

- **代码影响**：11 个 Python 文件、1 个 JavaScript 文件（Electron 主进程）
  - `src/python/modules/tts/text_to_speech.py` — 播放后端 + 临时文件清理
  - `src/python/modules/skill_loader/skill_loader.py` — 子进程目标函数 + 权限校验
  - `src/python/server/conversation.py` — 异步回调 await
  - `src/python/modules/audio/audio_pipeline.py` — 事件循环引用
  - `src/python/server/main.py` — 回调连接 + 手势双重分发修复
  - `src/python/modules/llm/llm_provider.py` — 流式解析 + 重复事件
  - `src/python/modules/fusion/identity_fusion.py` — 自动发现接入
  - `src/python/modules/camera/camera_pipeline.py` — 延迟导入
  - `src/python/modules/state/state_machine.py` — 唤醒词状态扩展
  - `src/python/modules/pose/gesture_classifier.py` — 走近手势检测
  - `src/electron/main/main.js` — 托盘退出逻辑
- **依赖变更**：Python 新增可选依赖 `pygame` 或 `playsound`（替代 winsound 播放 MP3）
- **破坏性变更**：无。所有修复保持现有 API 契约不变
