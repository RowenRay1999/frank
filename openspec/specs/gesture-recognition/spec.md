# gesture-recognition — 手势分类

## ADDED Requirements

### Requirement: 预定义手势分类
系统 SHALL 使用规则引擎对连续姿态帧序列进行分类，识别 4 种预定义手势：raise_hand（举手）、point（指向）、wave（挥手）、come_closer（走近）。分类 SHALL 在每 30 帧（约 1s @ 30fps）滑动窗口上运行。

#### Scenario: 举手检测
- **WHEN** 手腕关键点（左手或右手）的 Y 坐标高于鼻尖 Y 坐标，且持续 >= 1 秒（30 帧）
- **THEN** 系统输出 GestureEvent，`gesture_type` 为 `"raise_hand"`，`confidence` >= 0.7

#### Scenario: 指向检测
- **WHEN** 食指指尖到手腕的向量延长线与摄像头平面的交点落在屏幕范围内，且手臂伸展（肘部角度 > 120 度），持续 >= 0.5 秒
- **THEN** 系统输出 GestureEvent，`gesture_type` 为 `"point"`，包含 `direction` 字段描述指向方向

#### Scenario: 挥手检测
- **WHEN** 手腕关键点 X 坐标在 1 秒内出现 >= 3 次方向反转（左右摆动），振幅 > 0.05（归一化坐标）
- **THEN** 系统输出 GestureEvent，`gesture_type` 为 `"wave"`

#### Scenario: 走近检测
- **WHEN** 鼻尖 Z 坐标（深度）在 2 秒内减小 > 0.1（归一化坐标），且人脸 bbox 面积增大 > 30%
- **THEN** 系统输出 GestureEvent，`gesture_type` 为 `"come_closer"`

#### Scenario: 无匹配手势
- **WHEN** 滑动窗口内的关键点序列不匹配任何预定义手势模式
- **THEN** `classify_gesture()` 返回 GestureEvent，`gesture_type` 为 `"none"`，`confidence` < 0.5

### Requirement: 手势防抖
系统 SHALL 对同一手势类型的连续触发实施防抖（debounce），同类型手势两次触发之间至少间隔 3 秒。

#### Scenario: 防抖阻止重复触发
- **WHEN** 系统在 t=0 时触发 `raise_hand` 手势
- **AND** 在 t=1.5 秒时再次检测到举手
- **THEN** 第二次举手被忽略，不产生 GestureEvent

#### Scenario: 防抖超时后允许触发
- **WHEN** 系统在 t=0 时触发 `raise_hand` 手势
- **AND** 在 t=4 秒时再次检测到举手
- **THEN** 第二次举手正常触发 GestureEvent

### Requirement: 关键点质量门控
系统 SHALL 仅使用 visibility > 0.5 的身体关键点和 confidence > 0.5 的手部关键点进行手势分类。低于阈值的关键点 SHALL 在分类计算中被忽略。

#### Scenario: 低质量帧跳过
- **WHEN** 连续 10 帧中超过 50% 的身体关键点 visibility < 0.5
- **THEN** 滑动窗口重置，不执行手势分类

#### Scenario: 部分遮挡仍可识别
- **WHEN** 下半身关键点 visibility < 0.5，但上半身（肩膀以上）关键点 visibility > 0.7
- **THEN** 举手和指向手势仍可正常检测（仅依赖上半身关键点）

### Requirement: 自定义手势注册
系统 SHALL 允许用户通过演示一段完整动作来注册自定义手势。注册流程：用户触发注册 → 系统录制 N 帧关键点序列 → 存储为自定义手势模板。

#### Scenario: 注册自定义手势成功
- **WHEN** 用户触发 `gesture.register` 命令，提供 `name: "my_fist"`
- **AND** 用户在 3 秒内演示完整拳击动作
- **THEN** 系统录制关键点序列，计算归一化模板，存储到 `custom_gestures` 表，返回 `gesture_id`

#### Scenario: 注册超时
- **WHEN** 用户在注册开始后 10 秒内未演示任何动作
- **THEN** 注册自动取消，返回超时错误

#### Scenario: 注册名称冲突
- **WHEN** 用户注册名称与已有自定义手势重复
- **THEN** 返回错误提示 "手势名称已存在，请使用其他名称"

### Requirement: 自定义手势匹配
系统 SHALL 使用 DTW（Dynamic Time Warping）算法将实时关键点序列与所有已注册自定义手势模板进行匹配。匹配分数 >= 阈值（默认 0.65）时触发 GestureEvent。

#### Scenario: DTW 匹配成功
- **WHEN** 用户执行已注册手势 `my_fist`，DTW 距离归一化后相似度 >= 0.65
- **THEN** 系统输出 GestureEvent，`gesture_type` 为 `"custom"`，`gesture_id` 为已注册手势的 ID

#### Scenario: DTW 匹配失败
- **WHEN** 用户执行未注册的任意动作
- **THEN** 所有已注册手势的 DTW 相似度均 < 0.65，不产生 custom 手势事件

#### Scenario: 多手势匹配取最高分
- **WHEN** 用户动作与两个已注册手势的相似度分别为 0.72 和 0.68
- **THEN** 系统仅返回相似度最高 (0.72) 的手势事件

### Requirement: 手势配置
系统 SHALL 通过 `config/frank.yaml` 的 `gesture` 节配置手势识别参数。

#### Scenario: 自定义 DTW 阈值
- **WHEN** 用户设置 `gesture.dtw_threshold: 0.75`
- **THEN** 自定义手势匹配仅相似度 >= 0.75 时触发

#### Scenario: 禁用手势识别
- **WHEN** 用户设置 `gesture.enabled: false`
- **THEN** 手势分类和自定义手势匹配均停止执行
