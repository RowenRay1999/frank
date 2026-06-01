## Why

从摄像头/麦克风采集人脸 embedding 和声纹 embedding，经融合引擎匹配确认身份，到前端身份面板展示人物信息——这条端到端链路存在多处数据断层和事件缺口，导致实时识别结果无法反映到身份面板、自动发现的未标识访客不会出现在前端列表、面板在打开后不会随识别事件刷新。此变更系统性修复这些断点，打通整条链路。

## What Changes

- **修复前端身份面板不响应实时识别事件**：`identity.confirmed` 事件到达时除更新顶栏头像/名称外，同时刷新身份面板人物列表（已识别成员区 + 待识别访客区）
- **新增未标识访客自动发现事件广播**：融合引擎在 `_check_auto_discovery` 创建/更新未标识人物后，通过 WebSocket 广播 `identity.unknown` 事件（含 `person_id`、`display_name`、`appearance_count`、`is_new`）给所有前端客户端
- **新增 `identity.person_list_changed` 事件**：在成员信息更新（识别确认、角色变更、新增访客等）后广播，前端收到后自动刷新面板数据
- **修复 `renderPersonList` 未标识人物显示名称字段映射**：将 `p.serial_name` 改为 `p.display_name`
- **修复 `identity.unknown` 事件载荷为空的问题**：在事件中填充自动发现的人脸信息
- **前端新增活跃识别状态指示**：在身份面板中标注当前被识别的活跃人物（高亮边框或标记）
- **将前端 identity 面板的人物列表数据源从"仅面板打开时一次性拉取"改为"事件驱动 + 面板打开时拉取"双路径刷新**

## Capabilities

### New Capabilities

- `identity-live-sync`: 身份识别结果到前端面板的实时同步——确认、变更、未知事件驱动面板人物列表刷新

### Modified Capabilities

- `identity-fusion`: `identity.unknown` 事件载荷需包含未标识人物信息（person_id, display_name, is_new）；`_check_auto_discovery` 需在创建/更新记录后触发广播
- `member-management`: 前端 `renderPersonList` 字段映射修正；面板需响应 `identity.person_list_changed` 事件自动刷新

## Impact

- **Python 服务端**: `identity_fusion.py` — `_check_auto_discovery()` 返回结果传递给事件回调；`_state_to_dict()` 增加 auto_discovered 信息；`_emit_identity_unknown()` 携带完整载荷
- **Python 服务端**: `main.py` — `on_identity_unknown()` 广播携带完整未标识人物信息；新增 `on_person_list_changed` 或复用现有机制通知前端刷新
- **Electron 主进程**: `main.js` — `handleMessage()` 已有 `identity.unknown` 转发，无需变更（载荷自动透传）
- **Electron 预加载**: `preload.js` — 已有 `onIdentityUnknown` 监听，无需变更
- **Electron 渲染进程**: `app.js` — `onIdentityUnknown` 和 `onIdentityConfirmed` 回调中追加 `loadPersonaPanel()` 调用；修复 `renderPersonList` 字段映射
- **数据库**: 无 schema 变更
