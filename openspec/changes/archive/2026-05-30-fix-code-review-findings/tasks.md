## 1. P0 CRITICAL — TTS 播放修复

- [x] 1.1 安装 `playsound` 依赖（更新 requirements.txt）
- [x] 1.2 替换 `text_to_speech.py` 中 Windows 分支的 `winsound.PlaySound` 为 `playsound(file_path)`，保留 try/except 回退
- [x] 1.3 在 `speak()` 方法中添加 finally 块调用 `os.unlink(tmp.name)` 清理临时 MP3 文件（同时修复临时文件泄露）

## 2. P0 CRITICAL — 技能子进程修复

- [x] 2.1 将 `skill_loader.py` 中 `execute_skill()` 内的嵌套函数 `_run_in_subprocess` 提取为模块级函数 `_run_skill_subprocess(path, params_json, q)`
- [x] 2.2 修复子进程函数内 `json` 模块的显式导入（`import json` 在函数体内）
- [x] 2.3 在 `execute_skill()` 中校验 `manifest.min_user_level` vs 当前用户角色等级，不满足时返回权限错误（同时修复授权绕过）

## 3. P0 CRITICAL — 对话异步回调修复

- [x] 3.1 在 `conversation.py` 的 `process_speech()` 和 `handle_text_input()` 中，为 `_on_user_message`、`_on_assistant_message`、`_on_sub_state_change` 回调添加 `await` + `asyncio.iscoroutinefunction` 检查
- [x] 3.2 在 `conversation.py` 的 `_change_sub_state()` 中为 `_on_sub_state_change` 回调添加 `await` + `iscoroutinefunction` 检查

## 4. P0 CRITICAL — 音频事件循环修复

- [x] 4.1 在 `AudioPipeline.__init__()` 中添加 `self._main_loop = None` 初始化
- [x] 4.2 在 `AudioPipeline.start()` 方法中保存 `self._main_loop = asyncio.get_running_loop()`
- [x] 4.3 重构 `_handle_vad()` 和 `_detect_wake_word()` 中的事件发射逻辑，统一使用 `self._main_loop` 替代 `asyncio.get_event_loop()`

## 5. P0 CRITICAL — Electron 托盘退出修复

- [x] 5.1 在 `main.js` 的 `mainWindow.on('close')` 处理器开头添加 `if (app.isQuitting) return;` 跳过 `event.preventDefault()`

## 6. P0 CRITICAL — Ollama 流式解析修复

- [x] 6.1 将 `llm_provider.py` 中 `OllamaProvider.generate_stream()` 改为缓冲区逐行拼接（处理 TCP 分片边界）
- [x] 6.2 修复 `LLMManager.chat()` 中流式成功时 `_on_response` 被触发两次的问题（移除 `_stream_with_fallback` 中的冗余调用）

## 7. P1 HIGH — STT/LLM/TTS 回调连接

- [x] 7.1 在 `main.py` 的 `main()` 函数中，STT/LLM/TTS 模块初始化后连接 6 个缺失的回调 setter
- [x] 7.2 使用 lambda + `asyncio.create_task(broadcast_event(...))` 模式创建回调包装

## 8. P1 HIGH — 自动发现接入

- [x] 8.1 在 `identity_fusion.py` 的 `_process_loop()` 中，当 `new_state.status == UNKNOWN` 且有最近人脸证据时调用 `_check_auto_discovery(face_emb)`
- [x] 8.2 在 `submit_face_evidence()` 中保存最近人脸嵌入引用，供 `_process_loop` 中的自动发现使用

## 9. P1 HIGH — Camera Pipeline 延迟导入

- [x] 9.1 删除 `camera_pipeline.py` 顶层的 `import mediapipe as mp`
- [x] 9.2 在 `CameraPipeline.start()` 方法内添加 try/except 包裹的延迟导入和初始化
- [x] 9.3 在 `_detect_with_mediapipe()` 中添加 `self._face_detector is None` 空值保护

## 10. P1 HIGH — 状态机唤醒词扩展

- [x] 10.1 删除 `state_machine.py` 中 `case 'wake_word'` 分支的状态限制条件，使唤醒词从任意状态均可触发 Chat 转换

## 11. P2 MEDIUM — 走近手势修复

- [x] 11.1 在 `gesture_classifier.py` 的 `_detect_come_closer()` 中，改用肩宽变化（归一化坐标距离）替代 MediaPipe 相对 Z 坐标作为深度代理
- [x] 11.2 使用窗口首尾肩宽均值对比（增幅 > 8% 视为走近），无需额外传递 bbox 信息

## 12. P2 MEDIUM — 手势双重分发修复

- [x] 12.1 删除 `main.py` 中 `on_pose_frame()` 内的冗余 `on_gesture_detected(event)` 调用（PoseModule._dispatch_gesture 已处理）

## 13. 验证

- [x] 13.1 验证所有修改的文件语法正确（Python: `python -m py_compile`，JS: `node --check`）— 10/10 Python + 1/1 JS 全部通过
- [x] 13.2 验证 `requirements.txt` 中 `playsound>=1.3.0` 依赖已添加
