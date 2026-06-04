## ADDED Requirements

### Requirement: Per-frame face bbox refresh
摄像头管线 SHALL 在每帧检测到人脸时更新缓存的 bbox 坐标，而非仅在 0→N 人脸出现事件时更新一次。

#### Scenario: Continuous face detection updates bbox
- **WHEN** 摄像头连续多帧检测到同一人脸且人脸在画面中移动
- **THEN** `_last_face_bbox` 应反映最新一帧的人脸边界框坐标

#### Scenario: Face disappears and reappears
- **WHEN** 人脸从画面消失后又重新出现
- **THEN** `_last_face_bbox` 应在人脸重新出现时更新为新的坐标

### Requirement: Face thumbnail for unidentified visitors
系统 SHALL 在自动发现未标识访客时捕获其人脸缩略图并持久化存储。

#### Scenario: New visitor auto-discovered
- **WHEN** 融合引擎检测到未匹配的新人脸并通过 `auto_discovery` 创建新访客记录
- **THEN** 系统 SHALL 从当前帧截取该访客的人脸缩略图（128×128 JPEG）
- **AND** 缩略图文件 SHALL 保存到 `data/faces/` 目录
- **AND** 文件路径 SHALL 通过 `update_unidentified_thumbnail` 写入 `unidentified` 表

#### Scenario: Existing visitor re-identified
- **WHEN** 融合引擎检测到已存在的未标识访客再次出现
- **THEN** 系统 SHALL 更新该访客的人脸缩略图
- **AND** 新的缩略图文件 SHALL 覆盖或替换旧的路径

### Requirement: Face thumbnail for identified members uses current bbox
已标识成员确认身份时的人脸缩略图截取 SHALL 使用最新的 bbox 坐标（与当前帧对齐）。

#### Scenario: Identity confirmed with current frame
- **WHEN** 融合引擎确认成员身份（CONFIRMED 状态）
- **THEN** 截取的人脸区域 SHALL 基于最近一帧的人脸 bbox
- **AND** 截取的缩略图应反映当前画面中的人脸位置（而非数秒前的位置）
