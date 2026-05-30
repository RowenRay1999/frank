## Context

Frank 项目初始化代码（commit a129330）经过系统性代码评审，发现 15 个缺陷。其中 6 个 CRITICAL 缺陷阻塞核心用户场景（TTS 无声、技能崩溃、对话无响应、音频事件丢失、退出失效、Ollama token 丢失）。本次设计覆盖全部 15 个修复的技术决策。

## Goals / Non-Goals

**Goals:**
- 修复全部 15 个已确认缺陷，恢复所有核心用户路径
- 保持现有模块接口和 API 契约不变
- 在 Windows 10/11 目标平台上验证修复有效性

**Non-Goals:**
- 不重构架构（事件总线、配置统一等架构优化留待后续）
- 不添加新功能
- 不引入新的外部依赖（除非必要）

## Decisions

### D1: TTS 播放后端 — `playsound` 替代 `winsound`

**选择**: 使用 `playsound` 库（pip install playsound）替代 `winsound.PlaySound`

**替代方案**:
- `pygame.mixer`: 功能强大但依赖体积大（~6MB），对简单 MP3 播放过重
- `pydub` + `pyaudio`: 需要额外安装 ffmpeg，部署复杂
- 先转 WAV 再播: 增加 I/O 开销

**理由**: `playsound` 是纯 Python 包，不依赖 ffmpeg，在 Windows 上通过 `winmm.dll` 原生支持 WAV/MP3，API 简单（`playsound(file_path)` 阻塞播放），完美匹配当前使用模式。

### D2: 技能子进程 — 模块级函数替代嵌套函数

**选择**: 将 `_run_in_subprocess` 提取为 `skill_loader.py` 的模块级函数，通过 `args` 传递所有参数

**替代方案**:
- `subprocess.Popen` + 独立脚本: 需要额外维护一个子进程入口脚本
- `concurrent.futures.ProcessPoolExecutor`: API 更简洁但不改变根本问题（仍需 pickle 序列化）
- `cloudpickle`: 可序列化嵌套函数但不希望引入非标准依赖

**理由**: 模块级函数是 Python multiprocessing 在 Windows spawn 模式下的标准做法，无额外依赖。

### D3: 对话异步回调 — 统一 `await` + `iscoroutinefunction` 检查

**选择**: 在 `conversation.py` 所有回调调用处添加 `await`，使用与 `audio_pipeline.py` 一致的 `iscoroutinefunction` 检测模式

**替代方案**:
- 所有回调强制改为同步: 会破坏 main.py 中已有的 async 回调
- 引入事件总线: 架构变更超出本次修复范围

**理由**: 与项目现有模式一致（audio_pipeline.py 中的 `_emit_*` 方法已正确实现此模式）。

### D4: 音频事件循环 — 启动时缓存 loop 引用

**选择**: 在 `AudioPipeline.__init__()` 中保存 `asyncio.get_running_loop()` 引用到 `self._main_loop`，后台线程使用 `self._main_loop.call_soon_threadsafe()` 调度

**替代方案**:
- 使用 `asyncio.new_event_loop()` 在子线程创建新循环: 无法与主循环通信
- 使用 `asyncio.run_coroutine_threadsafe()` 配合全局 loop 变量: 不如实例属性清晰

**理由**: 在 `start()` 方法（async 上下文）中获取运行中循环并存储，后续后台线程直接引用，避免 `get_event_loop()` 的 RuntimeError。

### D5: Electron 退出 — 检查 `app.isQuitting` 标志

**选择**: 在 `mainWindow.on('close')` 处理器开头添加 `if (app.isQuitting) return;` 跳过 preventDefault

**替代方案**:
- 移除 close 拦截改用 `app.on('before-quit')`: 会改变窗口关闭行为预期
- 在托盘退出点击中调用 `app.exit(0)`: 强制退出但跳过清理

**理由**: 最小改动，与 `before-quit` 中的 `app.isQuitting = true` 配合，退出时窗口正常关闭。

### D6: Ollama 流式 — 逐行读取 NDJSON

**选择**: 使用 `resp.content.readline()` 逐行读取，每行独立解析 JSON

**替代方案**:
- 手动实现缓冲区拼接: 复杂且易出错
- 使用 `aiohttp` 的 `resp.json()`: 不支持流式

**理由**: `aiohttp.StreamReader.readline()` 原生支持按换行符读取，完美匹配 Ollama 的 NDJSON 格式。

### D7: 回调连接 — 在 main() 中连接所有 8 个缺失回调

**选择**: 在 `main.py` 的 `main()` 中，模块初始化后立即调用各自的 `set_on_*` 方法，连接到对应的 `broadcast_event` 包装函数

具体连接:
- `stt_module.set_on_transcription(async (result) => broadcast_event('stt.transcription', result))`
- `llm_manager.set_on_token(...)`, `set_on_response(...)`, `set_on_error(...)`
- `tts_module.set_on_start(...)`, `set_on_complete(...)`, `set_on_unavailable(...)`

### D8: 其它修复

| Bug | 决策 |
|-----|------|
| mediapipe 顶层导入 | 将 `import mediapipe` 移入 `start()` 方法内，try/except 包装，失败时仅 MediaPipe 回退不可用 |
| 唤醒词状态扩展 | 删除 `state_machine.py` 中 `if self._state in (State.AUTH, State.CHAT)` 的条件限制，唤醒词从任意状态转入 Chat |
| 自动发现接入 | 在 `IdentityFusionEngine._process_loop()` 中，当 `new_state.status == UNKNOWN` 且有有效人脸嵌入时，调用 `_check_auto_discovery(face_emb)` |
| 技能授权 | 在 `SkillLoader.execute_skill()` 中读取 `manifest.min_user_level`，与传入的当前用户 role 比较 |
| 走近手势 | 改用 bbox 面积变化比例（当前帧面积 / 历史帧面积均值）替代 Z 坐标作为深度代理 |
| 手势重复分发 | 删除 `main.py:on_pose_frame` 中 `if event and event.gesture_type != 'none'` 后的 `await on_gesture_detected(event)` 调用 |
| LLM 双重事件 | 删除 `LLMManager.chat()` 方法末尾 `self._on_response` 调用（流式成功时 `_stream_with_fallback` 已触发） |
| TTS 临时文件 | 在 `text_to_speech.py` 的 `speak()` 方法 finally 块中添加 `os.unlink(tmp.name)` |

## Risks / Trade-offs

- **[Risk] `playsound` 在部分 Windows 系统上可能因缺少 codec 而失败** → Mitigation: 保留 try/except 回退到当前 winsound 行为（静默失败但记录日志）
- **[Risk] 技能从嵌套函数改为模块级函数可能影响变量闭包语义** → Mitigation: 所有依赖数据通过 args 显式传递，不依赖闭包
- **[Risk] 走近手势改用 bbox 面积可能与原 Z 轴检测语义不完全一致** → Mitigation: 面积变化是更可靠的深度代理（相机成像原理保证近大远小）
