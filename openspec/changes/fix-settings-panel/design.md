# Design: 修复设置界面功能缺陷

## 1. 键名修复：`llm.api_base` → `llm.base_url`

**根因**：HTML 表单使用 `data-key="llm.api_base"`，但后端 YAML 和 LLM Provider 代码使用 `llm.base_url`。

**决策**：修改 HTML 和 JS 中的键名以匹配后端 — 后端和 OpenSpec llm-integration 规格均使用 `base_url`。

**影响文件**：
- `src/electron/renderer/index.html:138` — 修改 `data-key` 属性
- `openspec/changes/fix-ui-pages-no-implementation/specs/settings-panel/spec.md` — 更新规格中的字段名引用（如有）

## 2. 设备列表加载修复

**根因**：`loadDeviceLists()` 在 [app.js:356](src/electron/renderer/app.js#L356) 定义但无任何调用点。

**决策**：在 `openPanel('settings')` 流程中调用 `loadDeviceLists()`。由于该函数已正确处理空值（try-catch 包裹、null 检查），只需添加调用点。

**调用位置**：[app.js:197](src/electron/renderer/app.js#L197) — 紧接 `loadSettings()` 之后。

## 3. 幽灵键处理

**根因**：HTML 表单中的 `privacy.auto_clean` / `privacy.clean_days` / `privacy.notify_days` / `tts.volume` 在 Python 默认值和 YAML 中不存在。

**决策**：
- `privacy.*` 键：在 Python `_get_defaults()` 和 Electron `getDefaultConfig()` 中注入 `privacy` 配置段。这些是面向未来的预留功能。
- `tts.volume`：在 Python `_get_defaults()` 的 `tts` 段中注入 `volume: 0.8`（0.0-1.0 范围）。UI 滑块保持 0-100（用户友好），在 JS 自动保存时转换为 0.0-1.0。

## 4. 前后端默认配置同步

**决策**：以 Python `_get_defaults()` 为权威源，更新 Electron `getDefaultConfig()` 使其完全一致。新增 `wakefree`、`visual_intent`、`multi_output`、`tasks`、`pose`、`gesture` 等段到 Electron 默认值中。

**策略**：不在两个地方重复维护 — 改为在 `config.js` 中引用一份与 Python 一致的默认值映射表。Phase 1 先手动同步，后续可以考虑自动生成。

## 5. 配置段 UI 增量补充

**决策**：本次只补充最常用的 3 个配置段。其余段留待后续 PR 按需添加。

| 配置段 | 包含控件 | 理由 |
|--------|---------|------|
| 🆕 唤醒免提 (wakefree) | 启用开关、人脸要求开关、人脸窗口秒数 | 影响核心免提体验 |
| 🆕 手势识别 (gesture) | 启用开关、DTW 阈值滑块、防抖秒数 | 用户常需调整灵敏度 |
| 🆕 任务管理 (tasks) | 最大重试次数、历史保留小时数 | 影响任务执行体验 |
| ⏩ 其余段 (visual_intent 等) | — | 留待后续 PR |

## 6. LLM Provider 选择器

在 LLM 配置组中增加一个下拉选择器 `data-key="llm.provider"`，选项：`openai`（OpenAI / Azure OpenAI）、`ollama`（本地 Ollama）。

## 7. tts.volume 值域映射

HTML 滑块：`min="0" max="100" step="5"` → 用户看到百分比。
JS 自动保存时：`value = Math.round(el.value) / 100` → YAML 存储 0.0-1.0。
JS 表单填充时：`el.value = Math.round(val * 100)` → 滑块显示百分比。

## 8. 加载错误处理

在 `loadSettings()` 中添加 8 秒超时计时器：
- 超时后显示"配置加载超时，请检查服务状态" + "重试"按钮
- `settings.current` 到达后清除计时器
- 重试按钮重新调用 `loadSettings()`

## 9. 服务端值校验

在 [main.py](src/python/server/main.py) 的 `settings.update` 处理中添加校验函数 `_validate_config_update(partial)`：
- `llm.temperature`：0.0 - 2.0
- `llm.max_tokens`：正整数
- `camera.detection_confidence`：0.0 - 1.0
- `wake_word.confidence_threshold`：0.0 - 1.0
- `tts.volume`：0.0 - 1.0（写入前已由前端映射）
- `tts.speed`：0.5 - 3.0

校验失败返回 `error` 消息包含具体字段和约束。

## 10. 低优先级修补

- `onSettingsCurrent` → 添加 `PanelManager.isOpen($('settingsPanel'))` 守卫
- 在设置面板底部添加"恢复默认配置"按钮（发送 `settings.reset`，后端实现为写入默认值并返回）
