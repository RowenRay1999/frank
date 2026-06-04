# Tasks: 修复设置界面功能缺陷

## Wave 1 — 阻断级修复 (BLOCKER)

- [ ] **1.1** 修复 `llm.api_base` → `llm.base_url` 键名不匹配
  - 文件：[index.html:138](src/electron/renderer/index.html#L138) — `data-key="llm.api_base"` → `data-key="llm.base_url"`
  - 文件：[index.html:138](src/electron/renderer/index.html#L138) — `placeholder` 保持不变 (`https://api.openai.com/v1`)
  - 验证：打开设置面板 → LLM 配置组的 API 地址字段应正确显示 YAML 中 `base_url` 的值；修改后应在 YAML 的 `llm.base_url` 键下生效

- [ ] **1.2** 为 `loadDeviceLists()` 添加调用点
  - 文件：[app.js:197](src/electron/renderer/app.js#L197) — 在 `if (name === 'settings') loadSettings();` 后增加 `loadDeviceLists();`
  - 验证：打开设置面板 → 音频设备/摄像头设备下拉框应有具体设备列表

## Wave 2 — 高严重性修复 (HIGH)

- [ ] **2.1** 同步 Python `_get_defaults()` 与 Electron `getDefaultConfig()`
  - 文件：[config.py:106-160](src/python/shared/config.py#L106-L160) — 以 Python 为权威源，向 `_get_defaults()` 注入缺失段（如有）
  - 文件：[config.js:117-127](src/electron/main/config.js#L117-L127) — 补齐 `microphone` 缺失字段 (`bits_per_sample`, `ring_buffer_seconds`, `pre_trigger_seconds`, `silence_threshold_ms`)；补齐 `logging.format`；补齐 `wake_word.model`；新增 `wakefree`, `visual_intent`, `multi_output`, `tasks`, `pose`, `gesture`, `privacy` 配置段
  - 验证：删除 `config/frank.yaml` 后启动应用 → Python 和 Electron 应使用一致的默认值

- [ ] **2.2** 在 Python/Electron 默认值中注入 `privacy` 配置段
  - 文件：[config.py](src/python/shared/config.py) — `_get_defaults()` 中新增 `'privacy': {'auto_clean': True, 'clean_days': 30, 'notify_days': 3}`
  - 文件：[config.js](src/electron/main/config.js) — `getDefaultConfig()` 中新增对应段
  - 验证：设置面板打开 → privacy 控件应从默认值正确填充

- [ ] **2.3** 在 Python/Electron 默认值中注入 `tts.volume` 字段
  - 文件：[config.py](src/python/shared/config.py) — `tts` 段增加 `'volume': 0.8`
  - 文件：[config.js](src/electron/main/config.js) — `tts` 段增加 `volume: 0.8`
  - 文件：[app.js:329-339](src/electron/renderer/app.js#L329-L339) — 在 change 事件处理中对 `tts.volume` 做值域映射：发送时 `value = Math.round(el.value) / 100` (percentage → 0.0-1.0)
  - 文件：[app.js:292-305](src/electron/renderer/app.js#L292-L305) — 在 `populateSettingsForm` 中对 `tts.volume` 做反向映射：接收到 0.0-1.0 时 `el.value = Math.round(val * 100)` (→ 0-100 滑块)
  - 验证：拖动音量滑块 → YAML 写入 0.0-1.0 范围；重新打开面板 → 滑块正确显示百分比

- [ ] **2.4** 新增 LLM Provider 选择器到设置 UI
  - 文件：[index.html](src/electron/renderer/index.html) — LLM 配置组顶部新增 `<select data-key="llm.provider" class="settings-select">`，选项 `openai` / `ollama`
  - 验证：选择 Ollama → YAML 中 `llm.provider` 应为 `ollama`

- [ ] **2.5** 补充 3 个高频配置段的 UI 编辑入口
  - 文件：[index.html](src/electron/renderer/index.html) — 在设置表单中新增以下分组：
    - **手势识别 (gesture)**：启用开关 (`gesture.enabled`)、DTW 阈值滑块 (`gesture.dtw_threshold`, 0.3-0.95, step 0.05)、防抖秒数 (`gesture.debounce_seconds`, 1-10, step 1)
    - **唤醒免提 (wakefree)**：启用开关 (`wakefree.enabled`)、人脸要求开关 (`wakefree.face_required`)、人脸窗口秒数 (`wakefree.face_window_seconds`, 1-10, step 1)
    - **任务管理 (tasks)**：最大重试次数 (`tasks.max_retries`, 1-10)、历史保留小时数 (`tasks.history_retention_hours`, 1-168)
  - 验证：3 个新分组应可折叠、控件正确绑定 data-key、修改后自动保存到 YAML

## Wave 3 — 中严重性修复 (MEDIUM)

- [ ] **3.1** 添加 settings.get 加载超时与错误处理
  - 文件：[app.js:286-289](src/electron/renderer/app.js#L286-L289) — `loadSettings()` 中增加 8 秒超时计时器，超时后显示"配置加载超时"提示 + "重试"按钮
  - 文件：[index.html](src/electron/renderer/index.html) — `settingsLoading` 区域预留错误提示 DOM 结构
  - 验证：断开 WebSocket → 打开设置面板 → 8 秒后应显示超时提示和重试按钮

- [ ] **3.2** 添加服务端配置值校验
  - 文件：[main.py:382-392](src/python/server/main.py#L382-L392) — 在 `settings.update` 处理中增加 `_validate_config_update()` 校验函数
  - 校验规则：
    - `llm.temperature`：float，0.0 ≤ value ≤ 2.0
    - `llm.max_tokens`：int，value > 0
    - `camera.detection_confidence`：float，0.0 ≤ value ≤ 1.0
    - `wake_word.confidence_threshold`：float，0.0 ≤ value ≤ 1.0
    - `tts.speed`：float，0.5 ≤ value ≤ 3.0
    - `tts.volume`：float，0.0 ≤ value ≤ 1.0
    - `gesture.dtw_threshold`：float，0.0 ≤ value ≤ 1.0
  - 校验失败时返回 `{ type: "error", payload: { code: "VALIDATION_FAILED", message: "字段 xxx 值不合法: ..." } }`
  - 验证：通过 WebSocket 发送 `{ type: "settings.update", payload: { llm: { temperature: 999 } } }` → 应收到 error 响应

## Wave 4 — 低优先级修复 (LOW)

- [ ] **4.1** `onSettingsCurrent` 添加面板状态守卫
  - 文件：[app.js:1179](src/electron/renderer/app.js#L1179) — 包裹 `PanelManager.isOpen($('settingsPanel'))` 检查
  - 验证：设置面板关闭时收到 `settings.current` → 不触发 DOM 操作

- [ ] **4.2** 添加"恢复默认配置"功能
  - 文件：[index.html](src/electron/renderer/index.html) — 设置面板底部增加 `<button id="btnResetDefaults">恢复默认配置</button>`
  - 文件：[app.js](src/electron/renderer/app.js) — 点击后弹出确认对话框，确认后发送 `{ type: "settings.reset" }`
  - 文件：[main.py](src/python/server/main.py) — 新增 `settings.reset` case，调用 `update_config(_get_defaults())` 写回 YAML，返回 `settings.current`
  - 文件：[config.js:117](src/electron/main/config.js#L117) — 确保 `getDefaultConfig()` 与 Python `_get_defaults()` 完全一致（已在 2.1 中同步）
  - 验证：点击恢复默认 → 确认 → 所有表单控件恢复为默认值 → YAML 文件被默认值覆盖

## 验证清单

- [ ] E2E-1：打开设置面板 → 5+3=8 个配置分组全部可见 → 控件正确回显 YAML 当前值
- [ ] E2E-2：修改 LLM API 地址 → 失焦后自动保存 → 检查 YAML `llm.base_url` 已更新
- [ ] E2E-3：拖动音量滑块 → 松开后自动保存 → YAML `tts.volume` 为 0.0-1.0 范围
- [ ] E2E-4：切换麦克风设备 → 下拉框应有设备列表 → 选择后显示"重启后生效"
- [ ] E2E-5：断开 WebSocket → 打开设置面板 → 8 秒后显示超时提示 → 点击重试
- [ ] E2E-6：点击恢复默认 → 确认 → 所有控件恢复默认值 → 重新打开面板验证持久化
- [ ] E2E-7：修改 LLM Provider 为 ollama → 保存 → YAML 确认 → 重启后 LLM 应使用 Ollama
