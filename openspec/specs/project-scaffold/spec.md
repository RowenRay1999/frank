# Frank 项目骨架规范 — project-scaffold

> **文档编号**: F-SPEC-PS-01  
> **版本**: 1.0  
> **日期**: 2026-05-30  
> **状态**: 草案  
> **负责人**: Rowen  
> **关联能力**: `project-scaffold`

---

## 概述

本文档定义 Frank（弗兰克）项目的项目骨架规范，涵盖目录结构、虚拟环境、Node.js 项目配置、Python 项目配置、配置文件、应用入口点以及开发脚本。项目骨架是整个系统的搭建基础，所有后续能力（摄像头管线、音频管线、状态机、UI 壳、进程通信）均部署在此骨架之上。

---

## ADDED Requirements

### Requirement: 项目目录结构
The system MUST 遵循统一的目录树规范，将 Electron 前端代码置于 `src/electron/`，Python 推理服务代码置于 `src/python/`，技能插件置于 `skills/`，配置文件置于 `config/`，文档置于 `docs/`，测试置于 `tests/`。

#### Scenario: 创建完整目录树
- **WHEN** 执行 `setup.bat` 或 `setup.sh` 初始化项目
- **THEN** 项目根目录下必须存在以下完整目录结构：
```
frank/
├── src/
│   ├── electron/
│   │   ├── main/                    # Electron 主进程代码
│   │   │   ├── index.js             # 主进程入口
│   │   │   ├── window-manager.js    # 窗口管理器
│   │   │   ├── tray-manager.js      # 系统托盘
│   │   │   ├── ws-client.js         # WebSocket 客户端
│   │   │   └── audio-manager.js     # 音频管理
│   │   └── renderer/                # 渲染进程代码
│   │       ├── index.html           # 渲染进程 HTML 入口
│   │       ├── styles/              # 样式文件
│   │       └── scripts/             # 渲染进程 JavaScript
│   ├── python/
│   │   ├── server/                  # WebSocket 服务器与主入口
│   │   │   ├── __init__.py
│   │   │   └── main.py             # Python 服务入口点
│   │   ├── modules/                 # AI 推理模块
│   │   │   ├── __init__.py
│   │   │   ├── face_detector.py     # MediaPipe 人脸检测
│   │   │   ├── vad.py               # Silero VAD
│   │   │   ├── wake_word.py         # OpenWakeWord 唤醒词
│   │   │   └── ring_buffer.py       # 环形缓冲区
│   │   └── shared/                  # 共享工具模块
│   │       ├── __init__.py
│   │       ├── config.py            # 配置加载
│   │       └── logger.py            # 日志工具
│   ├── skills/                      # 技能插件目录（占位）
│   │   └── __init__.py
│   ├── config/                      # 配置文件
│   │   └── frank.yaml               # 主配置文件
│   ├── docs/                        # 项目文档
│   ├── tests/                       # 测试目录
│   │   ├── electron/                # Electron 侧测试
│   │   └── python/                  # Python 侧测试
│   ├── .venv/                       # Python 虚拟环境
│   ├── package.json                 # Node.js 项目配置
│   ├── requirements.txt             # Python 依赖清单
│   ├── setup.bat                    # Windows 初始化脚本
│   ├── setup.sh                     # Unix 初始化脚本
│   ├── dev.bat                      # Windows 开发模式脚本
│   └── dev.sh                       # Unix 开发模式脚本
```
- **WHEN** 任意后续能力模块向项目中添加代码
- **THEN** Electron 代码必须放置在 `src/electron/main/` 或 `src/electron/renderer/` 下，Python 代码必须放置在 `src/python/server/`、`src/python/modules/` 或 `src/python/shared/` 下

#### Scenario: 目录隔离性检查
- **WHEN** Electron 项目构建时
- **THEN** `src/python/` 目录下的内容不会被包含在 Electron 打包产物中

---

### Requirement: Python 虚拟环境与依赖管理
The system SHALL 在项目根目录下提供 `.venv/` 虚拟环境，并通过 `requirements.txt` 声明所有 Python 依赖。

#### Scenario: 创建虚拟环境并安装依赖
- **WHEN** 用户运行 `setup.bat` 或 `setup.sh`
- **THEN** 系统必须在 `src/.venv/` 下创建 Python 虚拟环境，并从 `src/requirements.txt` 安装以下精确依赖：
```
mediapipe>=0.10.0
silero-vad>=4.0
openwakeword>=0.4.0
websockets>=12.0
numpy>=1.26.0
opencv-python>=4.9.0
pyaudio>=0.2.14
pyyaml>=6.0
```
- **WHEN** Python 包安装完成后
- **THEN** Electron 主进程应能通过 `src/.venv/Scripts/python.exe`（Windows）或 `src/.venv/bin/python`（Unix）路径调用 Python 解释器

#### Scenario: 依赖一致性验证
- **WHEN** 持续集成流水线运行
- **THEN** `pip install -r src/requirements.txt` 必须成功且不报版本冲突

---

### Requirement: Node.js 项目配置
The system MUST 在 `package.json` 中配置 Electron 项目，声明 `electron`、`ws` 和 `electron-builder` 为依赖，并定义 `dev` 和 `build` 两个顶层 scripts。

#### Scenario: 定义 npm scripts
- **WHEN** 用户在项目根目录运行 `npm run dev`
- **THEN** Electron 以开发模式启动，加载 `src/electron/main/index.js` 作为主进程入口，渲染进程启用开发者工具
- **WHEN** 用户运行 `npm run build`
- **THEN** electron-builder 打包应用为 Windows 安装包，输出到 `dist/` 目录
- **WHEN** 执行 `npm install`
- **THEN** 以下依赖必须被正确解析并安装：
```json
{
  "devDependencies": {
    "electron": "^32.0.0",
    "electron-builder": "^25.0.0"
  },
  "dependencies": {
    "ws": "^8.0.0"
  },
  "scripts": {
    "dev": "electron src/electron/main/index.js",
    "build": "electron-builder",
    "start": "electron src/electron/main/index.js"
  }
}
```

---

### Requirement: 配置文件规范
The system SHALL 使用 `src/config/frank.yaml` 作为统一的 YAML 配置文件，包含 camera、microphone、wake_word、websocket、state_machine 和 logging 六个配置节。

#### Scenario: 加载完整配置
- **WHEN** Electron 主进程或 Python 推理服务启动时
- **THEN** 二者必须从 `src/config/frank.yaml` 读取配置，并解析为结构化对象
- **WHEN** `src/config/frank.yaml` 内容如下时：
```yaml
camera:
  device_id: 0
  width: 640
  height: 480
  fps: 30

microphone:
  device_id: 0
  sample_rate: 16000
  chunk_size: 320

wake_word:
  text: "Hey Frank"
  sensitivity: 0.5

websocket:
  port: 21901
  host: "127.0.0.1"

state_machine:
  timeouts:
    idle_to_aware: 0
    aware_to_auth: 10
    auth_to_chat: 5
    chat_idle_timeout: 300
    multi_auth_timeout: 10
    multi_person_debounce: 3

logging:
  level: "INFO"
  file_path: "logs/frank.log"
```
- **THEN** 各字段按对应类型被正确解析：`camera.device_id` 为整数 0，`microphone.sample_rate` 为整数 16000，`wake_word.text` 为字符串 `"Hey Frank"`，`websocket.port` 为整数 21901，`logging.level` 为字符串 `"INFO"`，`state_machine.timeouts.chat_idle_timeout` 为整数 300

#### Scenario: 配置文件缺失处理
- **WHEN** `src/config/frank.yaml` 不存在
- **THEN** 系统必须使用内置默认值继续启动，并在日志中输出警告

---

### Requirement: 应用入口点 — Electron 主进程
The system MUST 实现 `npm start` 启动流程：Electron 主进程启动 Python 子进程（从 `.venv` 调用），等待 WebSocket 就绪信号，然后创建渲染窗口。

#### Scenario: 正常启动流程
- **WHEN** 用户在命令行执行 `npm start`
- **THEN** Electron 主进程执行以下步骤：
  1. 读取 `src/config/frank.yaml` 获取 WebSocket 端口和主机地址
  2. 使用 `child_process.spawn` 从 `src/.venv/Scripts/python.exe`（Windows）或 `src/.venv/bin/python`（Unix）以 `-m src.python.server.main` 参数启动 Python 子进程
  3. Python 子进程 stdout 输出 `{"event":"ready","port":21901}` 作为就绪信号
  4. Electron 主进程收到就绪信号后，调用 `new BrowserWindow()` 创建渲染进程窗口，加载 `src/electron/renderer/index.html`
  5. Electron 主进程通过 `ws` 库连接到 `ws://127.0.0.1:21901`

#### Scenario: Python 子进程启动失败
- **WHEN** Python 子进程在 30 秒内未发出 `ready` 信号
- **THEN** Electron 主进程必须在渲染窗口显示"服务启动中..."提示，重试启动 Python 子进程，最多重试 3 次
- **WHEN** 3 次重试均失败
- **THEN** 渲染窗口显示"服务启动失败，请检查 Python 环境"错误页面，系统托盘图标显示错误状态

---

### Requirement: Python 入口点
The system MUST 实现 Python 侧入口点 `python -m src.python.server.main`，启动 WebSocket 服务器，初始化所有 AI 推理模块，并向 Electron 主进程发出就绪信号。

#### Scenario: Python 服务启动
- **WHEN** Python 进程以 `python -m src.python.server.main` 启动
- **THEN** 必须依次完成以下初始化：
  1. 读取 `src/config/frank.yaml` 配置
  2. 初始化日志系统（`logging` 节配置）
  3. 初始化各推理模块（face_detector、vad、wake_word、ring_buffer）
  4. 在 `127.0.0.1:21901` 上启动 WebSocket 服务器
  5. 向 stdout 输出 JSON 格式就绪信号：`{"event":"ready","port":21901}`
- **WHEN** Electron 主进程通过 WebSocket 发送 `{"type":"ping"}` 消息
- **THEN** Python 服务必须在 100ms 内回复 `{"type":"pong"}`

#### Scenario: 模块初始化失败
- **WHEN** 任一推理模块初始化失败（如摄像头不可用、模型文件缺失）
- **THEN** Python 服务必须记录错误日志但继续启动，以降级模式运行
- **WHEN** WebSocket 服务器启动失败（如端口被占用）
- **THEN** Python 服务必须在 10 秒内尝试下一个端口（21902, 21903...），并将实际端口写入就绪信号

---

### Requirement: 开发脚本
The system SHALL 提供 `setup.bat`/`setup.sh`（首次环境搭建）和 `dev.bat`/`dev.sh`（开发模式启动）两组脚本。

#### Scenario: 首次环境搭建脚本
- **WHEN** 用户在新机器上运行 `setup.bat`（Windows）或 `setup.sh`（Unix）
- **THEN** 脚本必须按顺序执行：
  1. 创建完整目录树
  2. 检查 Node.js 和 npm 版本是否满足要求（Node.js >= 20, npm >= 10）
  3. 检查 Python 版本是否满足要求（Python >= 3.11）
  4. 在 `src/.venv/` 下创建 Python 虚拟环境
  5. 通过 pip 安装 `src/requirements.txt` 中的依赖
  6. 在项目根目录下执行 `npm install`
  7. 如果 `src/config/frank.yaml` 不存在，从默认模板创建
  8. 输出成功信息

#### Scenario: 开发模式启动脚本
- **WHEN** 用户运行 `dev.bat`（Windows）或 `dev.sh`（Unix）
- **THEN** 脚本必须自动执行：
  1. 验证 `.venv/` 和 `node_modules/` 是否已安装（若未安装则提示先运行 setup 脚本）
  2. 启动 Python 推理服务进程（后台运行）
  3. 等待 Python 服务就绪信号（最长 30 秒）
  4. 启动 Electron 开发模式（`npm run dev`）
  5. 当 Electron 退出时，自动终止 Python 子进程并清理资源

#### Scenario: 跨平台兼容
- **WHEN** 在 Windows 上运行 `setup.bat`
- **THEN** 必须使用 `.bat` 批处理语法，不依赖 WSL 或 Unix 工具
- **WHEN** 在 Unix 系统（macOS/Linux）上运行 `setup.sh`
- **THEN** 必须使用 POSIX shell 语法，虚拟环境路径使用 `src/.venv/bin/python`

---

> **文档结束**
>
> **修订记录**:
> | 版本 | 日期 | 修改内容 | 作者 |
> |---|---|---|---|
> | 1.0 | 2026-05-30 | 初稿 | Rowen |
