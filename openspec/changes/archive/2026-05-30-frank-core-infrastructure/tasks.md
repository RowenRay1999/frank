## 1. 项目骨架搭建

- [x] 1.1 创建项目目录结构：`src/electron/main/`、`src/electron/renderer/`、`src/python/server/`、`src/python/modules/`（camera/、audio/、state/）、`src/python/shared/`、`skills/`、`config/`、`tests/`、`docs/`
- [x] 1.2 创建 `src/python/requirements.txt`：mediapipe、silero-vad、openwakeword、websockets、numpy、opencv-python、pyaudio、pyyaml，使用精确版本号
- [x] 1.3 创建 Python 虚拟环境 `.venv/`，执行 `pip install -r requirements.txt`
- [x] 1.4 创建 `package.json`：依赖 electron、ws、electron-builder，定义 scripts（dev、build、start），main 指向 `src/electron/main/main.js`
- [x] 1.5 创建 `config/frank.yaml` 配置文件：camera、microphone、wake_word（默认 "Hey Frank"）、websocket（host: localhost, port: 8765）、state_machine（各状态超时值）、logging（level: INFO, file: logs/frank.log）
- [x] 1.6 创建 Electron 主进程入口 `src/electron/main/main.js`：初始化窗口、spawn Python 子进程、建立 WebSocket 连接、应用生命周期管理
- [x] 1.7 创建 Python 推理服务入口 `src/python/server/main.py`：启动 asyncio WebSocket 服务（端口 8765）、初始化所有模块、发送 ready 信号
- [x] 1.8 创建开发脚本：`scripts/setup.bat`（创建 venv + pip install + npm install）、`scripts/dev.bat`（启动 Python 服务 + Electron 开发模式）

## 2. 进程通信桥

- [x] 2.1 实现 Python 端 WebSocket 服务器：消息路由框架（根据 `type` 字段分发到对应 handler）、消息序列化/反序列化（JSON）
- [x] 2.2 实现 Electron 端 WebSocket 客户端：连接管理（含重连退避 1s→2s→4s→8s→max 30s）、心跳（5 秒 ping/pong）
- [x] 2.3 定义消息信封格式：`{ type, id (UUID), timestamp (ISO8601), payload }`，响应消息含 `in_reply_to`
- [x] 2.4 实现所有 Phase 1 消息类型 handler（Electron→Python: camera.start/stop/configure, mic.start/stop/configure, state.get/transition, ping；Python→Electron: camera.face_detected/face_lost/frame/error, mic.voice_start/voice_end/wake_word/error, state.changed/current, pong, error）
- [x] 2.5 实现错误消息格式：`{ type: "error", payload: { code, message, recoverable, suggestion } }`
- [x] 2.6 实现端口冲突检测与自动迁移（8765→8766→...→8780），将实际端口写入 `.frank_port` 文件

## 3. 核心状态机

- [x] 3.1 实现状态枚举与定义：Idle（待机）、Aware（检测到人）、Auth（身份确认）、Chat（对话中）
- [x] 3.2 实现状态转换规则：Idle→Aware（人脸或声音检测到）、Aware→Idle（30s 无活动）、Aware→Auth（人脸持续 2s）、Auth→Chat（唤醒词触发）、Chat→Auth（5min 静默）、Auth→Idle（60s 无人脸）
- [x] 3.3 实现状态变更事件推送：每次转换发送 `state.changed` WebSocket 消息（含 from、to、timestamp、trigger）
- [x] 3.4 实现状态查询接口：响应 `state.get` 消息，返回当前状态名和已停留时长
- [x] 3.5 超时参数从 `config/frank.yaml` 读取，状态转换日志以 INFO 级别记录（含触发原因）

## 4. 摄像头采集管线

- [x] 4.1 实现摄像头设备枚举：OpenCV 扫描可用设备，返回设备列表（id、name、支持分辨率）
- [x] 4.2 实现帧捕获循环：OpenCV VideoCapture 640×480 RGB，自适应帧率（Idle=1fps, Aware=5fps, Auth/Chat=10fps），`__init__.py` 暴露 CameraPipeline 接口
- [x] 4.3 集成 MediaPipe Face Detector（short-range 模型）：每帧检测人脸，输出 bbox（x,y,width,height）+ confidence + landmarks
- [x] 4.4 实现检测事件推送：`camera.face_detected`（0→≥1 人脸）、`camera.face_lost`（≥1→0）、`camera.frame`（每帧检测结果，按状态频率限流）
- [x] 4.5 实现摄像头启动/停止命令处理（`camera.start`、`camera.stop`、`camera.configure`）
- [x] 4.6 实现错误处理：摄像头未找到（CAM_NOT_FOUND）、权限拒绝（CAM_PERMISSION_DENIED）、断连（CAM_DISCONNECTED），均含中文提示
- [x] 4.7 实现设备热插拔监听：新摄像头 → `camera.device_added`，当前摄像头断开 → 自动切换备选或降级模式

## 5. 麦克风采集管线

- [x] 5.1 实现麦克风设备枚举：PyAudio 扫描可用输入设备，返回设备列表（id、name、采样率、通道数）
- [x] 5.2 实现音频采集：16kHz / 16bit / mono PCM，PyAudio callback 模式，chunk 512 samples（~32ms），含自动增益控制
- [x] 5.3 实现 10 秒环形缓冲区：线程安全读写，事件触发时提取 [触发点-1.5s, 触发点+至静音] 音频段，`__init__.py` 暴露 AudioPipeline 接口
- [x] 5.4 集成 Silero VAD：每个 chunk 输出 speech_probability（0-1），阈值 0.5，推送 `mic.voice_start` / `mic.voice_end` 事件
- [x] 5.5 集成 OpenWakeWord：持续监听默认唤醒词 "Hey Frank"，置信度 ≥0.7 触发，推送 `mic.wake_word` 事件（含置信度分数），唤醒词需与人脸检测在 1s 窗口内重合才生效
- [x] 5.6 实现麦克风启动/停止命令处理（`mic.start`、`mic.stop`、`mic.configure`）
- [x] 5.7 实现错误处理：麦克风未找到（MIC_NOT_FOUND）、权限拒绝（MIC_PERMISSION_DENIED）、断连（MIC_DISCONNECTED），均含中文提示
- [ ] 5.8 验证性能：VAD 延迟 <10ms/chunk，唤醒词检测延迟 <100ms，总管线延迟 <150ms（需连接实际硬件运行验证）

## 6. 桌面 UI 壳

- [x] 6.1 实现窗口管理：紧凑模式 360×500px / 展开模式 800×600px，frameless 自定义标题栏，置顶切换，最小 300×400 最大 1200×900，窗口位置记忆（electron-store）
- [x] 6.2 实现自定义标题栏：状态指示器圆点（左）+ 状态文字 + 最小化/展开/关闭按钮（右），可拖拽移动窗口
- [x] 6.3 实现状态指示器：Idle=灰⚪、Aware=蓝🔵脉动、Auth=绿🟢、Chat=紫🟣脉动、降级=黄🟡，CSS animation 脉动效果
- [x] 6.4 实现聊天面板占位：欢迎语区域 + 空白消息列表（可滚动） + 禁用状态输入区（显示"语音监听中..."），Chat 状态时显示"正在听..."
- [x] 6.5 实现系统托盘：托盘图标常驻，右键菜单（显示/隐藏窗口、状态子菜单、设置（灰色）、退出），双击切换窗口，关闭窗口最小化到托盘
- [x] 6.6 实现设置面板入口（展开模式侧边栏或托盘菜单），显示占位文字"设置功能将在后续版本中开放"
- [x] 6.7 实现开机自启：Windows 注册表 Run 键写入，`config/frank.yaml` 的 `auto_start` 控制，默认启用
- [x] 6.8 实现 IPC 集成：contextBridge 暴露状态监听接口，渲染进程响应状态变更（更新指示器颜色、标题文字、面板内容），无轮询

## 7. 集成验证

- [ ] 7.1 端到端连通性测试：启动应用 → Python 服务就绪 → WebSocket 握手成功 → 摄像头+麦克风开始采集 → UI 显示 Idle 状态
- [ ] 7.2 人脸检测流程测试：有人出现在摄像头前 → 状态机 Idle→Aware→Auth → UI 指示器颜色变化（灰→蓝→绿）
- [ ] 7.3 唤醒词流程测试：人对摄像头说 "Hey Frank" → 状态机 Auth→Chat → UI 指示器变紫色脉动 → 聊天面板显示"正在听..."
- [ ] 7.4 超时回退测试：人离开摄像头 → Aware 30s 后回退 Idle → Auth 60s 后回退 Idle → UI 指示器恢复灰色
- [ ] 7.5 断连恢复测试：杀死 Python 进程 → Electron 自动重启子进程 → WebSocket 重连成功 → 状态恢复
- [ ] 7.6 设备异常测试：拔掉摄像头 → 降级模式（黄灯）+ 错误提示 → 插回摄像头 → 自动恢复
- [ ] 7.7 快速验证清单：执行 `scripts/dev.bat` 一键启动，按验收场景逐项确认
