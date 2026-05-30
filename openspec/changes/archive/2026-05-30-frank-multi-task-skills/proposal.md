## Why

前三个 Phase 完成了"单人识别+对话"闭环，但 Frank 的核心设计场景是**家庭共享设备**，天然存在多人同时在场的情况。当前系统无法处理第二个人走过来的场景——不能并行服务多人、不能把响应路由到不同输出设备、也不能处理耗时任务。Phase 4 补齐这最后三块拼图，让 Frank 成为一个完整的家庭工作助手。

## What Changes

- 实现多人检测与多人会谈模式：检测到 ≥2 人时自动切换模式，不中断当前会话，识别新来者后在后台等待指令
- 实现多输出设备路由：系统音频设备枚举、副屏/副音频设备分配、并行会话的用户-输出通道绑定
- 实现后台任务管理系统：命令分类（即时/托管）、托管任务生命周期（提交→排队→执行→完成/失败）、任务进度可查、三级异常处理
- 实现技能插件系统：插件目录结构（manifest.json + handler.py + prompt.md）、自动发现与加载、子进程隔离执行、多技能编排
- 实现任务仪表盘 UI：每用户任务列表、进度条、失败原因+解决方案、主人可查看所有任务

## Capabilities

### New Capabilities
- `multi-person-mode`: 多人检测与多人会谈模式——≥2 人检测 3 秒后进入、识别所有人身份、静默等待指令、不中断当前会话
- `multi-output-routing`: 多输出设备路由——音频设备枚举（WASAPI）、副屏检测、用户-输出通道绑定、并行会话输出隔离
- `task-management`: 后台任务管理系统——命令分类、托管任务生命周期、任务队列（同用户 FIFO + 跨用户并行）、三级异常处理（可恢复/需决策/不可恢复）、任务进度查询、会话恢复
- `skill-plugin-system`: 技能插件系统——标准化插件结构（manifest/prompt/handler）、启动时自动发现、子进程隔离执行（超时+内存限制）、LLM 编排多技能调用

### Modified Capabilities
- `state-machine`: 新增 Multi-Auth（识别所有人）→ Multi-Wait（静默等待）→ Multi-Chat（并行会话）多人状态分支，单人/多人模式平滑切换
- `camera-pipeline`: 多脸追踪——InsightFace 同时输出多张人脸 embedding，每帧推送所有检测到的人脸（而非仅第一个）
- `ui-shell`: 新增任务仪表盘面板、多人模式状态指示器（红色）、技能管理面板、副输出设备配置界面

## Impact

- **新增文件**：`src/python/modules/multi_person/`、`src/python/modules/task_manager/`、`src/python/modules/skill_loader/`、`skills/` 下内置技能（weather/schedule/reminder）
- **修改文件**：state_machine.py（多人分支）、camera_pipeline.py（多脸输出）、main.py（新模块注册）、renderer/*（任务面板+多人指示器）
- **配置新增**：`config/frank.yaml` 中 multi_output（副音频设备 ID、副显示器 ID）、tasks（超时/重试配置）
- **无破坏性变更**：所有 Phase 1-3 接口保持向后兼容
