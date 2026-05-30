## 1. 多人检测模式

- [x] 1.1 修改 `camera_pipeline.py`：多脸输出——每帧推送所有检测到的人脸（含各自 embedding），而非仅第一张
- [x] 1.2 实现人脸跨帧追踪：基于 embedding 余弦相似度（>0.7=同一人），维护 person_id → face 映射
- [x] 1.3 创建 `multi_person.py`：检测人数变化（≥2 人持续 3s → 进入多人模式，<2 人持续 5s → 退出）
- [x] 1.4 实现多人身份队列：每个检测到的人在融合引擎确认后加入等待队列，携带身份+角色上下文
- [x] 1.5 实现队列优先级：Owner 始终占据主槽位，同角色先到先服务

## 2. 多输出设备路由

- [x] 2.1 实现音频输出设备枚举：PyAudio + pywin32 WASAPI 扫描，返回设备列表推送到 Electron
- [x] 2.2 实现显示器枚举：Electron screen API，区分主屏/副屏
- [x] 2.3 实现用户-通道绑定：主用户→系统默认设备，副用户→预配置副设备
- [x] 2.4 实现并行输出隔离：主 TTS 走主音频设备，副 TTS 走副设备；单设备时副用户降级为文字通知
- [x] 2.5 通道释放：用户会话结束时释放绑定的输出设备

## 3. 后台任务管理系统

- [x] 3.1 创建 `task_manager.py`：任务数据模型（task_id, type, status, progress, created_at, user_id, role）
- [x] 3.2 实现 SQLite 任务持久化：tasks 表，应用重启后自动恢复未完成任务
- [x] 3.3 实现命令分类：LLM 输出 task_type（immediate/managed）+ estimated_duration
- [x] 3.4 实现托管任务生命周期：Submit → Queued → Executing → Completed/Failed
- [x] 3.5 实现任务队列：同用户 FIFO + 跨用户并行（独立资源池）+ 角色上下文携带
- [x] 3.6 实现三级异常处理：🟡 自动重试 3 次指数退避 / 🟠 暂停+通知+选项 / 🔴 通知原因+建议
- [x] 3.7 实现任务进度查询：用户随时问"我的任务好了吗？"→ 返回当前状态
- [x] 3.8 实现完成通知：Windows Toast + 对话面板消息追加

## 4. 技能插件系统

- [x] 4.1 定义插件标准结构：`skills/<name>/manifest.json` + `handler.py` + `prompt.md`
- [x] 4.2 实现插件自动发现：启动时扫描 `skills/` 目录，加载所有合法 manifest
- [x] 4.3 实现子进程隔离执行：multiprocessing.Process，stdin/stdout JSON 通信，超时+内存限制
- [x] 4.4 实现权限检查：manifest.permissions 声明与运行时校验
- [x] 4.5 实现 prompt 注入：所有插件 prompt.md 拼接进 LLM 系统提示词"可用能力"部分
- [x] 4.6 实现多技能编排：LLM 分解复杂指令 → 调用多个技能 → 汇总结果
- [x] 4.7 创建内置技能：weather（天气查询，mock）、schedule（日程管理，mock）、reminder（提醒，mock）
- [x] 4.8 实现热加载：`skills/` 目录文件变更检测 → 重新扫描 → 更新 LLM 上下文

## 5. 状态机升级

- [x] 5.1 新增多人状态分支：Multi-Auth（识别所有人）→ Multi-Wait（静默等待）→ Multi-Chat（并行会话）
- [x] 5.2 实现模式切换规则：Aware→Multi-Auth（≥2 人 3s）、Multi-Auth→Multi-Wait（全部识别完成）、Multi-Wait↔Chat+Multi-Wait（主用户对话）
- [x] 5.3 实现模式退出：人数降至 1 持续 10s → 回退单人模式

## 6. UI 升级

- [x] 6.1 实现任务仪表盘面板：任务列表（名称+进度条+状态），操作按钮（查看/重试），主人可看全部
- [x] 6.2 实现多人模式指示器：红色状态圆点，等待队列显示（排队人姓名列表）
- [x] 6.3 实现技能管理面板：已安装技能列表 + 启用/禁用开关 + 技能详情查看
- [x] 6.4 更新 renderer/app.js：新 IPC 事件监听（task.*, multi_person.*, skill.*, channel.*）
- [x] 6.5 更新 main.js/preload.js：新消息类型路由

## 7. 主模块集成

- [x] 7.1 更新 `main.py`：注册 multi_person_manager, task_manager, skill_loader 模块，接线回调
- [x] 7.2 更新 `config/frank.yaml`：新增 multi_output、tasks 配置段
- [x] 7.3 更新 WebSocket 消息路由：新增 multi_person.*, task.*, skill.* 消息类型

## 8. 集成验证

- [ ] 8.1 多人检测测试：2 人同时出现在摄像头前 3 秒 → 进入多人模式 → 红色状态指示
- [ ] 8.2 并行会话测试：A 在对话中，B 走近→排队→B 发指令→副输出设备响应
- [ ] 8.3 任务提交测试：用户说"帮我压缩照片文件夹"→ 任务进入队列→进度可查→完成通知
- [ ] 8.4 异常处理测试：任务磁盘满→暂停+通知+选项→用户选择后继续
- [ ] 8.5 插件加载测试：放置 skill 目录→重启→插件出现在技能列表→被 LLM 识别
- [ ] 8.6 模式回退测试：多人离开只剩 1 人→10s 后回退单人模式
