## Why

身份识别界面（identityPanel）中 `identity-face-thumb` 展示的人脸缩略图并非实际人脸识别采样时的抓图，导致用户无法直观确认系统识别的是哪张人脸。问题根因有二：(1) 摄像头管线 `_last_face_bbox` 仅在 0→N 人脸出现事件时更新一次，融合引擎确认身份时使用的 bbox 早已过期，截取的人脸区域与匹配时的实际人脸不符；(2) 未标识访客从未被截取人脸缩略图，`update_unidentified_thumbnail` 方法已实现但从未被调用。

## What Changes

- **修复 `_last_face_bbox` 更新时机**：从仅在首次人脸出现时更新改为每帧有人脸时都更新，确保 `on_identity_confirmed` 截取时 bbox 与当前帧对齐
- **新增未标识访客人脸截图**：在 `on_identity_unknown` 回调中捕获人脸缩略图并写入 `data/faces/` 目录，调用 `update_unidentified_thumbnail` 持久化路径
- **修复多人在场时 bbox 归属错误**：`faces[0]` 可能不属于被确认的成员 — 改为在 `_emit_face_detected` 中为每个检测到的人脸分别缓存 bbox，或使用 embedding 匹配来确定正确的 bbox

## Capabilities

### New Capabilities
- `face-thumbnail-capture`: 人脸缩略图截取与存储 — 确保每帧人脸 bbox 更新、未标识访客与已标识成员均能在身份事件中截取正确的人脸缩略图

### Modified Capabilities
<!-- 不涉及 spec 级别的需求变更 -->

## Impact

- **摄像头管线** (`camera_pipeline.py`): `_last_face_bbox` 更新策略改为每帧更新
- **融合引擎回调** (`main.py`): `on_identity_unknown` 新增人脸截图逻辑
- **身份融合引擎** (`identity_fusion.py`): 可选 — 传递匹配时的 bbox 信息以支持精确截图
- **前端** (`app.js`): 无需修改（已有 `face_thumbnail` 渲染逻辑）
- **成员管理器** (`member_manager.py`): 无需修改（`update_unidentified_thumbnail` 已实现）
