## Context

Frank 的身份识别链路涉及 5 层组件：

1. **摄像头管线** (`camera_pipeline.py`) → 提取人脸 embedding → `on_face_embedding` 回调
2. **音频管线** (`audio_pipeline.py`) → 提取声纹 embedding → `on_voiceprint` 回调
3. **融合引擎** (`identity_fusion.py`) → 双模态匹配 → 决策矩阵 → 事件 (confirmed/changing/unknown)
4. **服务端** (`main.py`) → 接收事件 → WebSocket `broadcast_event` → Electron
5. **前端** (`main.js` → `preload.js` → `app.js`) → IPC 转发 → 渲染 identity 面板

当前链路存在 4 个明确断点：

- **断点 A**: `identity.confirmed` 到达前端后仅更新顶栏，不刷新身份面板人物列表 — [app.js:721]
- **断点 B**: `_check_auto_discovery()` 创建/更新未标识访客后无任何事件广播 — [identity_fusion.py:235-258]
- **断点 C**: `identity.unknown` 事件载荷为空 `{}`，与 spec 要求的 `{person_id, display_name, is_new}` 不符 — [identity_fusion.py:325]
- **断点 D**: `renderPersonList` 使用 `p.serial_name` 但 DB 列是 `display_name` — [app.js:443]

此外，面板的数据加载模式是"仅打开时拉取一次"，缺乏事件驱动的持续刷新。

## Goals / Non-Goals

**Goals:**
1. 身份识别确认/变更时前端面板自动刷新人物列表
2. 新未标识访客自动发现后广播事件通知前端
3. `identity.unknown` 载荷携带完整的未标识人物信息
4. 修复前端字段映射错误
5. `identity.confirmed` 回调中也刷新面板（确保最新数据）

**Non-Goals:**
- 不引入新的 WebSocket 消息类型（复用现有 `identity.*` 事件通道）
- 不修改数据库 schema
- 不改变融合决策矩阵逻辑
- 不改变摄像头/音频管线的 embedding 提取逻辑
- 不添加轮询机制（纯事件驱动）

## Decisions

### D-1: 事件驱动面板刷新 vs 轮询

**选择**: 事件驱动。在 `onIdentityConfirmed`、`onIdentityUnknown` 回调中调用 `loadPersonaPanel()` 重新拉取 `member.list` + `member.pending`，重新渲染人物列表。

**替代方案**: 轮询（每 N 秒拉取 member.list）—— 增加无谓开销，延迟大。
**理由**: 融合引擎已正确触发 `identity.confirmed` 和 `identity.unknown` 事件，只需在事件消费端连接刷新逻辑。

### D-2: `identity.unknown` 载荷增强方案

**选择**: 在 `_check_auto_discovery` 中返回结构化的发现结果，在 `_process_loop` 的 UNKNOWN 分支中将其填充到 `_emit_identity_unknown` 的事件载荷中。

```python
# identity_fusion.py
def _check_auto_discovery(self, face_emb):
    ...
    return {'person_id': person_id, 'display_name': name, 
            'is_new': True, 'appearance_count': 1}
```

**替代方案**: 新增独立 `person.discovered` 事件类型 —— 增加复杂度，且语义上仍是 "identity unknown" 的后续动作。
**理由**: spec 已约定 `identity.unknown` 携带此信息，修正实现以匹配 spec 即可。

### D-3: 面板刷新时机

**选择**: 在以下 3 个事件回调中调用 `loadPersonaPanel()`：
- `onIdentityConfirmed`: 身份确认 → 可能有新的识别统计
- `onIdentityUnknown`: 可能有新创建的未标识访客
- 面板打开时 (`openPanel('identity')`): 保持现有行为

**理由**: 覆盖所有数据变更触发源，最小化刷新次数，不引入轮询。

### D-4: 字段映射修复

**选择**: `renderPersonList` 中 `p.serial_name` → `p.display_name`，直接在渲染时取 DB 返回的原生字段。

**替代方案**: 在 Python 端加 `serial_name` 别名 —— 增加不必要的序列化开销。
**理由**: DB 列即为 `display_name`，前端直接用。

## Risks / Trade-offs

- **[R1] 频繁刷新 → 防抖**：如果 `identity.confirmed` 短时间内连续触发（如证据累积过程中多次确认），会多次调用 `loadPersonaPanel()` → 多次 WebSocket 请求 `member.list`。**缓解**: `loadPersonaPanel` 本身是轻量请求；如需优化可加 500ms debounce，当前阶段先不加。

- **[R2] `identity.unknown` 载荷变大 → 不影响现有消费者**：现有前端 `onIdentityUnknown` 回调仅调用 `updateUserIdentity(null)`，新增的载荷字段不会干扰现有逻辑。

- **[R3] 面板未打开时的刷新 → 无谓请求**：如果面板未打开，`loadPersonaPanel()` 仍然会触发两次 WebSocket 请求（member.list + member.pending）。**缓解**: 在 `loadPersonaPanel` 中检查面板是否打开，仅面板打开时发送请求。

## Migration Plan

无 schema 迁移。变更仅涉及代码逻辑修复：

1. 修改 `identity_fusion.py` — `_check_auto_discovery` 返回值增强 + `_emit_identity_unknown` 载荷填充
2. 修改 `main.py` — 无需变更（transparent pass-through）
3. 修改 `app.js` — 事件回调中追加 `loadPersonaPanel()` + 字段映射修复
4. 重启服务即可生效，无需数据迁移

## Open Questions

- 是否需要为面板刷新加 debounce 以防止短时间内多次请求？建议先不加，观察实际行为。
- 已识别成员的面板卡是否需要显示实时置信度（而非仅数据库中的静态 `recognition_confidence`）？当前 spec 未覆盖此需求，暂不处理。
