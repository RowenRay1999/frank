## 1. Fusion Engine — Auto-discovery Broadcast

- [x] 1.1 修改 `identity_fusion.py` — `_check_auto_discovery()` 方法返回结构化结果（包含 `person_id`、`display_name`、`is_new`、`appearance_count`）而非当前松散 dict
- [x] 1.2 修改 `identity_fusion.py` — `_process_loop()` 中 UNKNOWN 分支将 `_check_auto_discovery` 的返回值传入 `_emit_identity_unknown()` 
- [x] 1.3 修改 `identity_fusion.py` — `_emit_identity_unknown()` 将自动发现结果注入事件载荷（`auto_discovered` 字段）（无需变更，已透传）
- [x] 1.4 修改 `identity_fusion.py` — `_state_to_dict()` 方法新增 `auto_discovered` 字段透出最新的自动发现信息
- [ ] 1.5 验证：启动 Frank，无注册成员时面对摄像头，确认 `identity.unknown` WebSocket 事件载荷包含 `auto_discovered` 对象

## 2. Server — Event Payload Pass-through

- [x] 2.1 检查 `main.py` — `on_identity_unknown()` 确认当前实现直接透传 `info` 字典到 `broadcast_event`，无需代码变更（已透传）
- [x] 2.2 若 `on_identity_unknown()` 当前丢弃 `info` 内容，修改为透传完整载荷（无需变更——当前已透传）
- [ ] 2.3 验证：WebSocket 客户端工具监听 `identity.unknown`，确认载荷包含 `auto_discovered` 字段

## 3. Frontend — Identity Panel Live Refresh

- [x] 3.1 修改 `app.js` — `onIdentityConfirmed` 回调中，在 `updateUserIdentity(data)` 之后，若身份面板已打开则调用 `loadPersonaPanel()` 刷新人物列表
- [x] 3.2 修改 `app.js` — `onIdentityUnknown` 回调中，在 `updateUserIdentity(null)` 之后，若事件包含 `auto_discovered` 且面板已打开则调用 `loadPersonaPanel()` 刷新人物列表
- [x] 3.3 修改 `app.js` — `loadPersonaPanel()` 添加面板打开检查：`PanelManager.isOpen($('identityPanel'))` 为 true 时才发送请求
- [x] 3.4 修改 `app.js` — `renderPersonList()` 中未标识人物显示名称路径从 `p.serial_name` 改为 `p.display_name`
- [x] 3.5 修复 `app.js` — `openPanel()` 中 `PanelManager.open(el)` 必须在数据加载函数之前调用（否则 `loadPersonaPanel` 的 `isOpen` 检查会拦截首次加载）
- [ ] 3.6 验证：打开身份面板，触发识别确认，确认面板人物列表自动刷新并反映最新数据

## 3b. Critical Bug Fix — Auto-discovery Logic Contradiction

- [x] 3b.1 修复 `identity_fusion.py` — 移除自动发现的前置条件 `face_evidence.is_valid and member_id is None`（逻辑矛盾：`is_valid` 要求 `member_id is not None`，但自动发现正是处理 `member_id is None` 的场景，条件永假导致自动发现从未触发）

## 4. End-to-End Integration Verification

- [ ] 4.1 验证：启动完整应用（Python + Electron），打开身份面板，在摄像头前让已注册成员出现 → 确认面板实时更新该成员的识别时间和置信度
- [ ] 4.2 验证：未注册人员在摄像头前出现 → 确认身份面板待识别区出现新的未标识访客记录（无需手动刷新面板）
- [ ] 4.3 验证：已注册成员离开后未注册人员出现 → 确认顶栏显示"访客/未识别"，面板待识别列表更新
- [ ] 4.4 验证：面板关闭时触发识别事件 → 确认不发送多余 WebSocket 请求（通过后端日志检查）
