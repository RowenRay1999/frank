## Context

身份识别界面的 `identity-face-thumb` 区域预期展示系统在识别过程中实际采样的人脸截图，帮助用户直观确认"系统看到了谁"。当前实现存在两个数据断层导致该区域无法正常展示。

**当前架构流程（有问题）**：

```
摄像头捕获帧 → 人脸检测 → _emit_face_detected（仅 0→N 转换时）
    ├─ _last_face_bbox = faces[0].bbox    ← 仅设置一次，永不更新
    └─ submit_face_evidence(embedding)    ← 仅首次提交
        └─ 融合引擎 _process_loop（0.2s 间隔）
            ├─ CONFIRMED → on_identity_confirmed → capture_face_thumbnail(_last_face_bbox)
            │   ↑ bbox 过期：可能来自几秒前的帧，与匹配时人脸不对应
            └─ UNKNOWN → on_identity_unknown → broadcast_event(...)
                ↑ 无截图：访客 face_thumbnail 永为 NULL
```

**核心问题**：
1. `_last_face_bbox` 仅在 `_emit_face_detected`（人脸出现事件，0→N 转换）中设置一次，后续帧中人脸移动后 bbox 不再更新。融合引擎确认身份（CONFIRMED）可能发生在数秒后，此时 bbox 坐标和帧内容均已偏移。
2. 未标识访客（UNKNOWN + auto_discovery）流程中从未调用 `capture_face_thumbnail` 和 `update_unidentified_thumbnail`，导致 `unidentified` 表的 `face_thumbnail` 字段始终为空。

## Goals / Non-Goals

**Goals:**
- 修复 `_last_face_bbox` 更新策略，使其在每帧有人脸时保持最新
- 为未标识访客补全人脸截图逻辑，确保 `unidentified.face_thumbnail` 有值
- 已标识成员的人脸缩略图与身份匹配帧对齐

**Non-Goals:**
- 不改变人脸检测频率或 embedding 提交频率（那是独立的性能/精度问题）
- 不处理多人同时在场时的精确人脸-身份匹配（当前架构假设单人场景）
- 不修改前端渲染逻辑（已有代码已正确处理 `face_thumbnail` 字段）

## Decisions

### D1: `_last_face_bbox` 改为每帧更新

**选择**：将 `_last_face_bbox` 的赋值从 `_emit_face_detected` 内部移到 `_capture_loop` 主循环中，在每次成功检测到人脸后更新。

**备选方案**：
- A（已选）：每帧更新 `_last_face_bbox`。改动最小（1行移动），风险最低。覆盖绝大多数使用场景（单人）。
- B：通过融合引擎传递匹配帧 bbox。需要在 `identity_fusion.py` 中缓存 bbox 随 embedding 一起流转，改动较大，但多人在场时更精确。
- C：按 embedding hash 匹配 bbox。复杂度最高，当前阶段收益有限。

**理由**：当前系统以单人交互为主，每帧更新足以解决 bbox 过期问题。多人场景留待后续专门处理。

### D2: 在 `on_identity_unknown` 中捕获人脸缩略图

**选择**：在 `main.py` 的 `on_identity_unknown` 回调中，当 `auto_discovered` 存在且 `_last_face_bbox` 可用时，执行与 `on_identity_confirmed` 相同的人脸截图流程。

**代码路径**：
```python
# main.py on_identity_unknown 新增逻辑
if info.get('auto_discovered') and camera_pipeline and camera_pipeline._last_face_bbox:
    person_id = info['auto_discovered'].get('person_id')
    if person_id:
        jpeg_bytes = camera_pipeline.capture_face_thumbnail(camera_pipeline._last_face_bbox)
        if jpeg_bytes:
            filename = f"unid_{person_id}_{int(time.time())}.jpg"
            filepath = faces_dir / filename
            filepath.write_bytes(jpeg_bytes)
            member_manager.update_unidentified_thumbnail(person_id, str(filepath.absolute()))
```

**理由**：复用已有的 `capture_face_thumbnail` 和 `update_unidentified_thumbnail` 方法，逻辑与已标识成员对称，降低维护成本。

### D3: 提取公共截图辅助函数

**选择**：将人脸截图+保存逻辑抽取为 `_save_face_thumbnail(person_id, is_member=True)` 辅助函数，供 `on_identity_confirmed` 和 `on_identity_unknown` 共用。

**理由**：两处截图逻辑 90% 相同，提取后避免代码重复，且后续多人场景扩展时只需修改一处。

## Risks / Trade-offs

- **[R1] 多人在场时 bbox 归属不精确**：`_last_face_bbox` 始终取 `faces[0]`，当画面中有多人时，截取的可能是错误的人脸。**缓解**：当前系统设计为单人场景，多人支持需要 embedding→bbox 映射（记录为后续改进项）。
- **[R2] UNKNOWN 事件频率**：`on_identity_unknown` 在 auto_discovery 发现新访客时触发，频率低（30 秒冷却），不会造成磁盘 IO 压力。**缓解**：已有的冷却机制足够。
- **[R3] 磁盘空间**：每次确认或发现都写入一张 128×128 JPEG（约 5-10KB），长期运行可能积累。**缓解**：后续可增加按 person_id 覆盖写入（同 ID 只保留最新一张）或定时清理。

## Open Questions

- 是否需要为 `on_identity_confirmed` 也已改为使用 embedding 对应的精确 bbox？当前设计先解决最紧迫的 bbox 过期和访客截图缺失问题，多人精确匹配作为后续改进。
