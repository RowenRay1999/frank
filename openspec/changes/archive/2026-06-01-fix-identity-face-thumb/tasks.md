## 1. 摄像头管线 — bbox 更新策略

- [x] 1.1 在 `_capture_loop` 主循环中，人脸检测成功后立即更新 `_last_face_bbox = faces[0]['bbox']`（从 `_emit_face_detected` 内部移出到主循环，确保每帧更新）
- [x] 1.2 保留 `_emit_face_detected` 中已有的 bbox 赋值（作为首次兜底，不影响语义）

## 2. 服务端 — 提取共用截图函数

- [x] 2.1 在 `main.py` 中新增 `_save_face_thumbnail(person_id, is_member: bool)` 辅助函数，封装截帧→保存→写库逻辑
- [x] 2.2 重构 `on_identity_confirmed` 使用新的共用函数替换内联截图代码

## 3. 服务端 — 未标识访客人脸截图

- [x] 3.1 在 `on_identity_unknown` 回调中，检测 `auto_discovered` 存在且 `camera_pipeline._last_face_bbox` 可用时，调用共用截图函数
- [x] 3.2 截图保存到 `data/faces/unid_{person_id}_{timestamp}.jpg`，调用 `member_manager.update_unidentified_thumbnail` 持久化路径

## 4. 验证

- [ ] 4.1 启动系统，确认已标识成员出现在摄像头前时，identityPanel 中 `identity-face-thumb` 显示正确人脸缩略图
- [ ] 4.2 确认未标识访客出现在摄像头前时，identityPanel 中该访客条目也显示人脸缩略图（不再显示占位符 badge）
- [ ] 4.3 确认 `data/faces/` 目录下有对应的 `unid_*` 文件生成
