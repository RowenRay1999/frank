## Context

Frank 第一期（核心基础设施）需要搭建一个完整的桌面应用骨架，从零开始。系统的设计文档已在 `docs/superpowers/specs/` 下完成 6 份规划，涵盖系统架构、身份识别、交互模型、任务管理、成员管理和技术选型。本期聚焦"让骨架跑通"——不涉及人脸匹配、声纹比对、LLM 集成等上层能力。

**当前状态**：绿场项目，仅有设计文档和 OpenSpec 框架。

**约束**：
- 仅支持 Windows 10/11（后续可扩展到 macOS/Linux）
- 生物特征处理必须在本地完成
- Python 推理服务作为独立子进程运行，与 Electron 通过 WebSocket 通信
- 用户设备需有摄像头和麦克风

## Goals / Non-Goals

**Goals:**
- 搭建 Electron + Python 双进程项目骨架，可一键启动
- 实现 Electron 主进程 ↔ Python 推理服务之间的 WebSocket 双向通信
- 实现核心状态机 Idle → Aware → Auth → Chat 的完整流转
- 实现摄像头采集 + MediaPipe 人脸检测管线（检测到人脸 → 推送事件）
- 实现麦克风采集 + 环形缓冲区 + VAD + 唤醒词管线（检测到 "Hey Frank" → 推送事件）
- 实现基础 UI 壳：紧凑窗口、状态指示器颜色变化、对话面板占位、系统托盘
- 建立项目目录规范与配置文件格式

**Non-Goals:**
- 人脸特征提取与身份匹配（InsightFace）— 第二期
- 声纹提取与比对（SpeechBrain ECAPA-TDNN）— 第二期
- 语音转文字（Whisper/faster-whisper）— 第三期
- 云端 LLM 集成 — 第三期
- 身份融合决策矩阵 — 第二期
- 多人模式与多输出路由 — 第四期
- 任务管理系统 — 第四期
- 技能插件系统 — 第四期
- 成员管理与自动发现 — 第二期
- 视觉意图识别（注视/点头/摇头）— 第三期
- 免唤醒指令 — 第三期

## Decisions

### D1: Electron 主进程架构采用服务管理器模式

**决策**：主进程作为"服务管理器"，负责启动/停止 Python 子进程、管理 WebSocket 连接生命周期、代理渲染进程请求到 Python 服务。

**替代方案**：
- A) 所有逻辑放主进程 — 主进程过于臃肿，Python 生态无法直接利用
- B) 渲染进程直连 Python — 绕过主进程，IPC 模型更简单但权限控制弱

**选择理由**：主进程作为桥接层，可以统一处理权限、设备授权、应用生命周期。渲染进程不直接接触系统资源，安全性更好。

### D2: Python 推理服务使用 asyncio + websockets 库

**决策**：Python 服务基于 `websockets` 库（asyncio）实现，消息格式为 JSON。

**替代方案**：
- A) FastAPI HTTP — REST 不适合持续流式推送（摄像头帧、音频块）
- B) gRPC — 配置复杂，WebSocket 更轻量且 Electron 端原生支持好

**选择理由**：WebSocket 支持双向推送，JSON 可读性强便于调试，asyncio 适合 I/O 密集型推理流水线。

### D3: 摄像头帧通过共享内存 + 事件通知，而非 WebSocket 逐帧传输

**决策**：摄像头帧数据量大（640×480 RGB ≈ 900KB/帧），不通过 WebSocket 传输原始帧。改用 Python 端直接通过 OpenCV 读取摄像头，Electron 只发控制指令（开始/停止/切换设备）。

**替代方案**：
- A) WebSocket 传 JPEG 编码帧 — 延迟可控但带宽浪费
- B) 共享内存（mmap）— 最快但跨平台兼容性差

**选择理由**：让 Python 端直接操作硬件最直接。Electron 通过 WebSocket 发送设备选择和参数配置，Python 返回检测事件（有人/无人、人脸坐标），不传输原始图像。后续如果需要在前端预览摄像头画面，可以传 JPEG 缩略图。

### D4: 音频流同理——Python 端直接通过 PyAudio 采集

**决策**：Python 推理服务直接通过 PyAudio 访问麦克风，在进程内完成环形缓冲、VAD、唤醒词检测。Electron 发送采集控制指令，Python 推送检测事件。

**选择理由**：Python 生态的 VAD（Silero）和唤醒词（OpenWakeWord）都需要直接访问音频流，放在 Python 端调用链路最短。音频数据量远小于视频（16kHz mono ≈ 32KB/s），但实时性要求高，放在推理服务内部处理避免 IPC 延迟抖动。

### D5: 配置文件采用 YAML 格式，统一管理

**决策**：`config/frank.yaml` 作为主配置文件，包含摄像头设备 ID、麦克风设备 ID、唤醒词文本、状态机超时参数、WebSocket 端口等。

**选择理由**：YAML 人类可读性好，支持注释（与 JSON 相比），Python 和 Node.js 均有成熟库。配置文件不存敏感信息（API Key 等走环境变量或系统凭据管理器）。

### D6: UI 采用纯 HTML/CSS/JS，不使用前端框架

**决策**：一期渲染进程使用原生 HTML/CSS/JavaScript，不引入 React/Vue 等框架。

**替代方案**：
- A) React + TypeScript — 开发体验好但增加构建步骤和包体积
- B) Vue 3 — 同样增加项目复杂度

**选择理由**：一期 UI 极其简单（状态指示器 + 对话面板占位），用框架是过度工程。后续 UI 复杂度提升时再评估引入轻量框架。

## Risks / Trade-offs

- **[R1] Python 子进程崩溃** → 主进程通过 `child_process` 的 `exit` 事件监听，崩溃后自动重启（最多 3 次，指数退避）。重启期间 UI 显示"服务重连中..."。
- **[R2] WebSocket 断连** → 主进程和渲染进程各自维护心跳检测（ping/pong 每 5 秒），断连后自动重连（退避策略：1s → 2s → 4s → 8s → max 30s）。
- **[R3] 摄像头/麦克风不可用** → 启动时检测设备可用性，不可用时以灰色指示器降级运行（仅对话面板可用）。热插拔支持：监听设备变更事件，设备就绪后自动恢复。
- **[R4] Python 依赖安装失败** → 提供预打包的 Python 环境（嵌入式 Python + pip 安装脚本），或在首次启动时引导用户运行安装脚本。CI 构建 PyInstaller 独立包作为长期方案。
- **[R5] Electron 内存占用偏高** → 一期接受 ~200MB 基线。后续通过懒加载渲染进程、优化 Chromium 启动参数控制。
- **[R6] 端口冲突（WebSocket 8765）** → 启动时检测端口可用性，被占用则递增尝试（8766, 8767...），将实际端口写入临时文件供 Electron 读取。

## Migration Plan

不适用——绿场项目，无迁移需求。

## Open Questions

- ~~Q1: 摄像头帧是否需要在前端实时预览？~~ → 一期不做预览，仅显示状态。后续在设置面板中加预览窗口。
- ~~Q2: Python 虚拟环境 vs 系统 Python？~~ → 使用项目内的 `.venv/` 虚拟环境，确保依赖隔离。
