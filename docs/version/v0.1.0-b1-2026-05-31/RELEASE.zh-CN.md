# Frank v0.1.0-b1 — 首个内测版本发布

**发布日期：** 2026-05-31
**版本号：** v0.1.0-b1
**类型：** Beta（内测）
**作者：** Rowen

---

## TL;DR

Frank 首个内测版本正式推出。这是一个面向桌面的 AI 助手平台，采用 Electron + Python 混合架构，集成了语音识别、摄像头管线、身份融合、大模型对话等核心能力。本版本搭建了完整的基础架构骨架，并完成了主面板 UI 的玻璃态视觉重构。

---

## ✨ 亮点

- **全窗口主面板 UI 重构** — 从 360×500 扩展至 800×600，采用 oklch 色彩空间与玻璃态视觉风格，三区域布局（状态/监控/导航），配合 Frank Orb 光球交互动画。
- **滑入式面板系统（PanelManager）** — 支持设置、成员、任务、身份、通知五大面板，实现非破坏性信息展示。
- **多模态感知管线** — 音频（STT/TTS）、摄像头（姿态/手势）、身份融合三大管线就绪，支持多人模式与免唤醒指令。
- **角色权限 + 技能插件体系** — 后端角色查询接口含权限矩阵与技能白名单，内置 reminder/schedule/weather 三个技能。
- **安全与稳定性修复** — 修复命令注入、异步调度、内存泄漏等多处安全隐患。

---

## 📋 Changelog

### 🚀 新功能

- **主面板全窗口重构** (`feat`): Electron 前端 v1→v3 全面重构，采用全窗口三区域布局（状态栏 / 监控区 / 导航栏）。引入 PanelManager 滑入式面板系统，支持设置、成员、任务、身份、通知五大面板。窗口尺寸从 360×500 扩展至 800×600。
  - 涉及文件：[src/electron/renderer/app.js](src/electron/renderer/app.js)、[src/electron/renderer/index.html](src/electron/renderer/index.html)、[src/electron/renderer/styles.css](src/electron/renderer/styles.css)、[design/main-panel.html](design/main-panel.html)、[design/css/app.css](design/css/app.css)

- **Frank Orb 光球交互动画** (`feat`): 新增呼吸/思考/粒子效果动画，配合玻璃态视觉风格。
  - 涉及文件：[src/electron/renderer/app.js](src/electron/renderer/app.js)、[src/electron/renderer/styles.css](src/electron/renderer/styles.css)

- **对话叠加层（Chat Overlay）** (`feat`): 新增对话叠加层与内联对话预览，支持非阻塞式对话交互。
  - 涉及文件：[src/electron/renderer/app.js](src/electron/renderer/app.js)

- **窗口控制 IPC** (`feat`): 新增最小化/关闭/退出确认/隐藏到托盘等功能，完善窗口生命周期管理。
  - 涉及文件：[src/electron/main/ipc.js](src/electron/main/ipc.js)、[src/electron/main/main.js](src/electron/main/main.js)、[src/electron/main/preload.js](src/electron/main/preload.js)

- **媒体设备枚举 API** (`feat`): preload 层新增媒体设备枚举 API 与角色/设置事件监听。
  - 涉及文件：[src/electron/main/preload.js](src/electron/main/preload.js)

- **四步注册向导** (`feat`): 新增身份→面部→声纹→确认四步注册流程。
  - 涉及文件：[src/electron/renderer/app.js](src/electron/renderer/app.js)

- **角色查询接口** (`feat`): 后端新增 `role.list` / `role.info` 接口，含权限矩阵与技能白名单。
  - 涉及文件：[src/python/modules/role/role_manager.py](src/python/modules/role/role_manager.py)

- **设置读写接口** (`feat`): 后端新增 `settings.get` / `settings.update` 接口，含 API Key 脱敏处理。
  - 涉及文件：[src/python/shared/config.py](src/python/shared/config.py)

- **配置深度合并与 YAML 回写** (`feat`): 新增 `config.py` 配置深度合并与 YAML 回写功能。
  - 涉及文件：[src/python/shared/config.py](src/python/shared/config.py)

- **设计令牌体系** (`feat`): 完整设计令牌体系——oklch 色彩空间、间距刻度、动效曲线。
  - 涉及文件：[design/css/app.css](design/css/app.css)、[src/electron/renderer/styles.css](src/electron/renderer/styles.css)

- **核心基础设施搭建** (`build`): 搭建项目骨架——Electron 前端 + Python 后端进程架构。实现核心 Python 模块：音频管线、摄像头管线、语音识别（STT）、语音合成（TTS）、姿态检测、手势识别、身份融合、大模型集成、多人模式、免唤醒指令、视觉意图、状态机、任务管理、角色权限、技能加载器。
  - 涉及文件：[src/python/](src/python/) 全部模块

- **技能插件系统** (`build`): 新增 reminder、schedule、weather 三个内置技能。
  - 涉及文件：[skills/reminder/](skills/reminder/)、[skills/schedule/](skills/schedule/)、[skills/weather/](skills/weather/)、[src/python/modules/skill_loader/skill_loader.py](src/python/modules/skill_loader/skill_loader.py)

### 🐛 问题修复

- **命令注入风险修复** (`fix`): Electron 主进程 `execSync` 命令注入风险，改用 `spawnSync` 参数化调用。
  - 涉及文件：[src/electron/main/main.js](src/electron/main/main.js)

- **异步调度安全修复** (`fix`): 音频管线 asyncio 事件循环安全隐患，使用存储的主循环引用替代动态获取。
  - 涉及文件：[src/python/modules/audio/audio_pipeline.py](src/python/modules/audio/audio_pipeline.py)

- **MediaPipe 导入崩溃修复** (`fix`): 摄像头管线 MediaPipe 模块导入崩溃，改为延迟导入并增加空指针保护。
  - 涉及文件：[src/python/modules/camera/camera_pipeline.py](src/python/modules/camera/camera_pipeline.py)

- **身份融合门控逻辑修复** (`fix`): 证据累积门控逻辑修复，增加评估去重与活跃时间更新限频。
  - 涉及文件：[src/python/modules/fusion/identity_fusion.py](src/python/modules/fusion/identity_fusion.py)

- **face_lost 抖动修复** (`fix`): 摄像头管线 `face_lost` 抖动问题，增加连续帧消抖和错误日志限频。
  - 涉及文件：[src/python/modules/camera/camera_pipeline.py](src/python/modules/camera/camera_pipeline.py)

- **托盘定时器内存泄漏修复** (`fix`): Electron 托盘定时器未清理导致的内存泄漏。
  - 涉及文件：[src/electron/main/main.js](src/electron/main/main.js)

### 🔧 改进

- **权限检查规格更新** (`fix`): 新增技能 `min_user_level` 权限检查规格与未标识访客自动发现规格。
  - 涉及文件：[.planning/reviews/REVIEW.md](.planning/reviews/REVIEW.md)

- **状态机规格更新** (`fix`): 唤醒词支持从 Idle/Aware 状态直接进入 Chat。
  - 涉及文件：[.planning/reviews/REVIEW.md](.planning/reviews/REVIEW.md)、[openspec/specs/state-machine/spec.md](openspec/specs/state-machine/spec.md)

- **项目配置完善** (`build`): 新增 `frank.yaml` 项目配置、`.gitignore`、开发脚本（`dev.bat`/`setup.bat`）。
  - 涉及文件：[config/frank.yaml](config/frank.yaml)、[scripts/dev.bat](scripts/dev.bat)、[scripts/setup.bat](scripts/setup.bat)

- **开发工具链集成** (`build`): 集成 CodeGraph 代码图谱、Understand-Anything 知识图谱分析工具。
  - 涉及文件：[.codegraph/](.codegraph/)、[.understand-anything/](.understand-anything/)

### 📝 文档

- **系统架构文档** (`docs`): 新建项目文档体系——系统架构、身份识别、交互模型、任务插件系统、成员生物识别、技术栈。
  - 涉及文件：[docs/specs/2026-05-30-frank-01-system-architecture.md](docs/specs/2026-05-30-frank-01-system-architecture.md) 等 6 份规格文档

- **OpenSpec 变更规划** (`feat`): 新增 4 份变更规划文档：`fix-app-exit-and-close`、`fix-ui-pages-no-implementation`、`integrate-legacy-panels-v2`、`redesign-main-panel-ui`。
  - 涉及文件：[openspec/changes/](openspec/changes/)

- **代码审查报告** (`fix`): 归档代码审查报告（REVIEW.md / REVIEW-FIX.md），记录 WR-03 至 WR-10 等安全发现。
  - 涉及文件：[.planning/reviews/REVIEW.md](.planning/reviews/REVIEW.md)、[.planning/reviews/REVIEW-FIX.md](.planning/reviews/REVIEW-FIX.md)

- **OpenSpec 规格汇总** (`build`): 汇总 23 份 OpenSpec 规格文档至 `openspec/specs/`，覆盖全部核心模块。
  - 涉及文件：[openspec/specs/](openspec/specs/)

---

## 📦 升级指南

本版本为首次内测发布，无需升级操作。

**环境准备：**
1. 安装 Node.js 18+ 和 Python 3.10+
2. 运行 `scripts/setup.bat` 安装依赖
3. 运行 `scripts/dev.bat` 启动开发模式

---

## ⚠️ 已知问题

- **UI 未实现页面路由** — 面板导航部分页面（设置详情、成员详情）尚未实现具体内容，目前展示占位界面。
- **大规模 UI 重构未自动化测试** — 主面板重构涉及大量前端代码变更，建议手动验证面板开合、角色查询、设置保存等交互流程。
- **核心管线需回归测试** — 代码审查修复后，建议回归测试音频、摄像头、身份融合三大核心管线。

---

## 👥 贡献者

- Rowen
- Rowen Ray

---

<details>
<summary>📜 完整提交列表</summary>

- `4143875` — feat: 重构主面板 UI：全窗口布局 + 面板系统 + 后端角色与设置接口集成
- `cf76047` — fix: 修复代码审查发现的安全隐患与异步调度问题
- `a129330` — build: 初始化 Frank 项目基础架构与核心模块
- `5d4341c` — build: 项目初始化
- `fca9738` — Initial commit

</details>
