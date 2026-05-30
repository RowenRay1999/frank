## Why

Frank（弗兰克）是一个面向家庭共享 Windows PC 的身份感知桌面助手。经过 6 份设计文档的完整规划，系统架构、交互模型、身份融合、任务管理和技术选型均已确定。当前需要从零搭建项目骨架——Electron 桌面壳 + Python AI 推理服务 + 进程间通信 + 基础状态机 + 摄像头/麦克风采集管线。没有这个基础，后续的人脸识别、声纹识别、对话交互等能力都无处挂载。

## What Changes

- 创建 Electron 桌面应用项目骨架（主进程 + 渲染进程）
- 创建 Python 推理服务项目骨架（WebSocket 服务 + AI 模块目录）
- 实现 Electron 主进程 ↔ Python 推理服务的本地 WebSocket 通信桥
- 实现基础状态机（Idle → Aware → Auth → Chat）及其生命周期管理
- 实现摄像头采集管线（MediaPipe 人脸检测，帧率可控）
- 实现麦克风采集管线（环形缓冲区 + Silero VAD + OpenWakeWord 唤醒词）
- 实现基础 UI 壳（紧凑窗口、状态指示器、对话面板占位）
- 建立项目目录规范、配置文件格式、启动脚本

## Capabilities

### New Capabilities
- `project-scaffold`: 项目骨架与目录规范，Electron + Python 双进程项目结构，启动脚本与配置管理
- `process-communication`: Electron 主进程与 Python 推理服务之间的本地 WebSocket 通信协议，消息路由与序列化
- `state-machine`: 核心状态机（Idle / Aware / Auth / Chat）的状态定义、转换规则、事件触发与生命周期管理
- `camera-pipeline`: 摄像头采集管线——设备枚举、帧捕获、MediaPipe 人脸检测、帧率控制、向推理服务推送帧数据
- `audio-pipeline`: 麦克风采集管线——音频流捕获、10 秒环形缓冲区、Silero VAD 语音活动检测、OpenWakeWord 唤醒词检测
- `ui-shell`: 基础桌面 UI 壳——Electron 窗口管理、紧凑/展开双模式、系统托盘、状态指示器、对话面板骨架

### Modified Capabilities
<!-- No existing capabilities to modify — this is a greenfield project -->

## Impact

- **新增代码**：Electron 项目（`package.json`、主进程入口、渲染进程 HTML/CSS/JS）、Python 项目（`requirements.txt`、WebSocket 服务入口、模块骨架）
- **新增目录**：`src/electron/`、`src/python/`、`skills/`（插件目录占位）、`config/`（配置文件）
- **依赖引入**：
  - Node.js: electron, ws, electron-builder
  - Python: mediapipe, silero-vad, openwakeword, websockets, numpy, opencv-python
- **无破坏性变更**：绿场项目，无现有代码受影响
