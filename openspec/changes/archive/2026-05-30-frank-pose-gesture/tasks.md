## 1. 数据库迁移

- [x] 1.1 在 `src/python/shared/database.py` 新增 `custom_gestures` 表（id, member_id, name, gesture_type, landmarks_template BLOB, created_at）和 `gesture_actions` 表（id, gesture_id, action, params_json, member_id, created_at）
- [x] 1.2 实现 schema_version 升级函数，从版本 1 自动迁移到版本 2

## 2. 配置文件

- [x] 2.1 在 `config/frank.yaml` 新增 `pose` 配置节（enabled, min_detection_confidence, min_tracking_confidence, model_complexity）
- [x] 2.2 在 `config/frank.yaml` 新增 `gesture` 配置节（enabled, dtw_threshold, debounce_seconds, window_frames）

## 3. PoseModule 核心实现

- [x] 3.1 创建 `src/python/modules/pose/__init__.py` 和 `src/python/modules/pose/pose_module.py`，实现 PoseModule 类
- [x] 3.2 实现 MediaPipe Pose (BlazePose) 初始化：33 关节点，`initialize()` 异步加载，`is_ready` 属性
- [x] 3.3 实现 `extract_pose(frame_rgb)` 方法：返回 PoseFrame 数据类（body_landmarks 33×4, left_hand_landmarks 21×3, right_hand_landmarks 21×3, timestamp）
- [x] 3.4 实现 `close()` 资源释放方法

## 4. 手势分类器实现

- [x] 4.1 创建 `src/python/modules/pose/gesture_classifier.py`，实现规则引擎手势分类器
- [x] 4.2 实现 `classify_gesture(sequence: list[PoseFrame])` 方法：识别 raise_hand, point, wave, come_closer 四种预定义手势
- [x] 4.3 实现举手检测规则：手腕 Y < 鼻尖 Y 持续 >= 1s
- [x] 4.4 实现指向检测规则：食指-手腕向量方向估算 + 肘部角度
- [x] 4.5 实现挥手检测规则：手腕 X 坐标方向反转计数 >= 3 次
- [x] 4.6 实现走近检测规则：鼻尖 Z 深度变化 + 人脸 bbox 面积变化
- [x] 4.7 实现滑动窗口缓冲（deque, maxlen=60）和关键点质量门控（visibility > 0.5）
- [x] 4.8 实现手势防抖：同类型手势触发间隔 >= 3s

## 5. 自定义手势系统

- [x] 5.1 在 `src/python/modules/pose/gesture_classifier.py` 实现 DTW 序列对齐算法
- [x] 5.2 实现 `register_custom_gesture(name, sequence)` 方法：录制关键点序列 → 归一化 → 存数据库 → 返回 gesture_id
- [x] 5.3 实现 `match_custom_gesture(sequence)` 方法：遍历已注册手势 → DTW 对齐 → 返回最高相似度 >= threshold 的手势
- [x] 5.4 实现 `delete_custom_gesture(gesture_id)` 方法

## 6. 手势动作槽系统

- [x] 6.1 在 PoseModule 中实现 `register_action_slot(gesture_type, callback)` 方法：pub-sub 注册
- [x] 6.2 实现 `_dispatch_gesture(gesture_event)` 方法：异步分发到所有匹配的订阅者
- [x] 6.3 实现默认手势动作绑定：raise_hand → 暂停对话, wave → 切换技能, come_closer → 激活助手, point → 上下文查询
- [x] 6.4 实现 `bind_custom_action(gesture_id, action, params)` 和 `unbind_custom_action(gesture_id)` 方法
- [x] 6.5 实现 `list_bindings()` 查询方法

## 7. CameraPipeline 集成

- [x] 7.1 在 `camera_pipeline.py` 添加 `_on_pose_frame` 回调和 `set_on_pose_frame` 注册接口
- [x] 7.2 在 Auth/Chat 状态的帧循环中，人脸检测完成后调用姿态帧回调
- [x] 7.3 确保 Pose/Hands 提取与人脸检测共享同一帧 RGB 数据，不重复解码

## 8. Python 服务端集成

- [x] 8.1 在 `main.py` 导入 PoseModule，创建全局实例 `pose_module`
- [x] 8.2 实现 `on_pose_frame(frame_rgb, frame_w, frame_h)` 回调：提取 PoseFrame → 分类手势 → 分发动作槽
- [x] 8.3 注册 camera_pipeline 的 `set_on_pose_frame` 回调
- [x] 8.4 添加 WebSocket 消息处理器：`gesture.register`, `gesture.bind`, `gesture.unbind`, `gesture.list_bindings`
- [x] 8.5 实现 `on_gesture_detected(gesture_event)` 广播回调：推送 `gesture.detected` 事件到 Electron
- [x] 8.6 连接手势事件到状态机：`come_closer` → state_machine.on_event('gesture_detected')

## 9. Electron 主进程集成

- [x] 9.1 在 `main.js` 的 `handleMessage()` 中添加 `gesture.detected` 等消息类型转发
- [x] 9.2 在 `preload.js` 的 `window.frankAPI` 中添加 `onGestureDetected` 事件监听器

## 10. UI 渲染器集成

- [x] 10.1 在 `renderer/app.js` 中添加 `gesture:detected` IPC 事件监听和浮层显示逻辑
- [x] 10.2 在 `renderer/index.html` 中添加手势浮层 DOM 元素（右下角 toast）
- [x] 10.3 在 `renderer/styles.css` 中添加手势浮层动画样式（fadeIn/fadeOut, 半透明背景, 图标+文字）

## 11. 验证（需硬件）

- [ ] 11.1 验证 MediaPipe Pose 模型可正常加载和推理
- [ ] 11.2 验证举手/挥手/指向/走近四种手势可被识别
- [ ] 11.3 验证自定义手势注册和 DTW 匹配
- [ ] 11.4 验证手势动作槽分发和默认绑定
- [ ] 11.5 验证 Electron UI 手势浮层提示
- [ ] 11.6 验证走近手势可触发 Idle → Aware 状态转换
- [ ] 11.7 验证举手手势可暂停/恢复对话
