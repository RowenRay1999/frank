# 进程间通信规范 (Process Communication)

## 概述

本文档定义了 Frank 系统中 Electron 主进程与 Python 推理服务之间的进程间通信规范。通信基于本地 WebSocket 协议（ws://localhost:8765），采用 JSON 消息格式，支持双向通信。

---

## ADDED Requirements

### Requirement: 消息格式定义
所有 WebSocket 消息必须遵循统一的 JSON 结构格式。

#### Scenario: 标准消息格式验证
- **WHEN** Electron 主进程向 Python 推理服务发送任何消息
- **THEN** 消息体必须包含顶层字段 `type`（字符串，标识消息类别）、`id`（字符串，UUID 格式，全局唯一）、`timestamp`（字符串，ISO8601 格式，表示消息发送时间）和 `payload`（对象，承载消息具体数据），示例：`{ "type": "ping", "id": "a1b2c3d4-...", "timestamp": "2026-05-30T10:00:00.000Z", "payload": {} }`

---

### Requirement: 消息类型定义
必须明确定义 Phase 1 中 Electron 与 Python 之间双向通信的所有核心消息类型。

#### Scenario: Electron 至 Python 消息类型枚举
- **WHEN** Electron 主进程向 Python 推理服务发送控制指令
- **THEN** 消息 `type` 字段必须为以下之一：`"camera.start"`（启动摄像头）、`"camera.stop"`（停止摄像头）、`"camera.configure"`（配置摄像头参数）、`"mic.start"`（启动麦克风）、`"mic.stop"`（停止麦克风）、`"mic.configure"`（配置麦克风参数）、`"state.get"`（查询当前状态）、`"state.transition"`（请求状态迁移）、`"ping"`（心跳探测）

#### Scenario: Python 至 Electron 消息类型枚举
- **WHEN** Python 推理服务向 Electron 主进程发送数据或事件
- **THEN** 消息 `type` 字段必须为以下之一：`"camera.frame"`（人脸检测结果，非原始帧）、`"camera.error"`（摄像头相关错误）、`"mic.audio_event"`（VAD 语音活动检测事件）、`"mic.wake_word"`（唤醒词检测结果）、`"mic.error"`（麦克风相关错误）、`"state.changed"`（状态已变更通知）、`"state.current"`（当前状态快照）、`"pong"`（心跳响应）、`"error"`（通用错误报告）

---

### Requirement: 连接生命周期管理
Python 推理服务必须优先启动 WebSocket 服务器，Electron 主进程随后以客户端身份发起连接。连接建立后须完成握手流程。

#### Scenario: 握手协议
- **WHEN** Electron 主进程成功连接到 Python 推理服务的 WebSocket 服务器
- **THEN** Electron 必须立即发送包含字段 `payload.app_version`（字符串，Electron 应用版本号）的 `"handshake"` 类型消息；Python 服务收到后必须响应包含 `payload.server_version`（字符串，Python 服务版本号）和 `payload.capabilities`（字符串数组，可用能力列表）的消息；在握手完成之前，双方不得发送其他业务消息

#### Scenario: 断线重连与指数退避
- **WHEN** WebSocket 连接意外断开
- **THEN** Electron 主进程必须按指数退避策略尝试重连：首次等待 1 秒，之后依次为 2 秒、4 秒、8 秒，达到最大上限 30 秒后保持该间隔持续重连，直至连接恢复

---

### Requirement: 心跳保活机制
双方须通过周期性 ping/pong 消息维持连接活性，并在检测到连接失效时触发重连。

#### Scenario: 心跳超时检测
- **WHEN** 连接保持正常
- **THEN** Electron 主进程每 5 秒发送一条 `type` 为 `"ping"` 的心跳消息，Python 推理服务必须在收到后立即以 `type` 为 `"pong"` 的消息响应

#### Scenario: 心跳丢失与重连触发
- **WHEN** Electron 主进程连续 3 次（即 15 秒内）未收到对应 `"ping"` 消息的 `"pong"` 响应
- **THEN** Electron 主进程必须记录警告日志（"WebSocket 心跳丢失，触发重连"），主动关闭当前连接，并立即进入指数退避重连流程

---

### Requirement: 消息 ID 与追踪
每条消息必须携带全局唯一的 UUID，响应消息须关联请求 ID，事件消息则无须关联。

#### Scenario: 请求-响应关联
- **WHEN** Electron 主进程发送一条 `type` 为 `"state.get"` 且 `id` 为 `"uuid-abc-123"` 的消息
- **THEN** Python 推理服务响应的消息必须包含 `payload.in_reply_to` 字段，其值为 `"uuid-abc-123"`，以明确标识该响应所对应的原始请求

#### Scenario: 事件消息无关联 ID
- **WHEN** Python 推理服务主动推送一条 `type` 为 `"camera.frame"` 或 `"mic.wake_word"` 的事件（非对任何请求的响应）
- **THEN** 消息中不得包含 `in_reply_to` 字段，接收方应将其视为主动推送的事件而非请求响应

---

### Requirement: 错误报告规范
Python 推理服务须以结构化格式报告错误，提供可操作的重试和恢复信息。

#### Scenario: 结构化错误消息
- **WHEN** Python 推理服务遇到摄像头初始化失败或模型加载异常等错误情况
- **THEN** 必须发送 `type` 为 `"error"` 的消息，其中 `payload` 必须包含：`code`（字符串，错误码，如 `"CAMERA_INIT_FAILED"`）、`message`（字符串，人类可读的错误描述）、`recoverable`（布尔值，指示错误是否可恢复）、`suggestion`（字符串，向用户或系统建议的修复操作，如 `"请检查摄像头连接或重启服务"`）

---

### Requirement: 端口冲突处理
当默认端口 8765 被占用时，Python 推理服务须自动选择可用端口并通知 Electron 主进程。

#### Scenario: 端口自动回退
- **WHEN** Python 推理服务启动时检测到端口 8765 已被其他进程占用
- **THEN** 服务必须依次尝试端口 8766、8767……直到 8780，选取第一个可用端口进行监听；成功绑定后，将实际使用的端口号写入临时文件 `.frank_port`（存放于约定的工作目录下），供 Electron 主进程读取以建立正确的连接地址
