## ADDED Requirements

### 1. 插件结构

每个插件位于 `skills/<name>/` 目录下，包含以下三个必需文件：

- **manifest.json** — 插件元数据声明，包含以下字段：
  - `name`: 插件名称
  - `trigger_keywords`: 触发关键词列表，LLM 据此匹配用户意图
  - `min_user_level`: 最低用户级别（如 `admin`、`user`、`guest`）
  - `permissions`: 所需权限列表（如 `network`、`file_read`、`file_write`）
  - `estimated_runtime`: 预计运行时长分类（`immediate`、`short`、`long`）
  - `output_type`: 输出类型（如 `text`、`json`、`markdown`）
- **handler.py** — 插件执行入口，必须暴露 `execute(params: dict) -> dict` 函数
- **prompt.md** — LLM 上下文提示词，描述插件的功能、使用场景及调用约束

### 2. 自动发现

系统启动时自动扫描 `skills/` 目录。每个包含有效 `manifest.json` 的子目录被识别为一个插件。`prompt.md` 的内容在启动时被注入到 LLM 系统提示词中，使 LLM 能够在对话中了解并使用这些插件。

### 3. 子进程隔离

每个插件 handler 在独立的 Python 子进程中运行，通过 stdin/stdout 进行 JSON 通信。提供两层超时控制：

- **即时任务（immediate）**：超时 10 秒
- **托管任务（managed）**：超时 30 分钟

内存限制：

- 即时任务：256 MB
- 托管任务：1 GB

子进程超时或超限时由主进程强制终止并返回错误信息。

### 4. 权限强制执行

所有权限声明在 `manifest.json` 的 `permissions` 字段中。执行前检查当前用户角色与插件声明的权限是否匹配。仅在清单中显式声明了 `network` 权限的插件才允许网络访问；仅在声明了 `file_read`/`file_write` 权限的插件才允许文件系统访问。未声明对应权限的访问请求将被拦截并报错。

此外，`manifest.json` 中的 `min_user_level` 字段 SHALL 在技能执行前与当前调用者的角色等级进行比较。如果调用者的角色等级低于 `min_user_level` 声明的等级，技能执行 MUST 被拒绝并返回权限不足错误。角色等级从高到低为：`owner` > `adult` > `child` > `guest`。

#### Scenario: 访客尝试执行需 owner 权限的技能

- **WHEN** 当前用户角色为 `guest`，调用 `min_user_level` 为 `owner` 的技能
- **THEN** 技能加载器拒绝执行，返回 `{'error': 'Permission denied: requires min_user_level=owner, current role=guest'}`

#### Scenario: 成人用户执行需 child 权限的技能

- **WHEN** 当前用户角色为 `adult`（角色等级 2），调用 `min_user_level` 为 `child`（角色等级 1）的技能
- **THEN** 技能加载器允许执行（adult > child），技能正常通过子进程运行

#### Scenario: min_user_level 未声明时默认允许

- **WHEN** manifest.json 中未设置 `min_user_level` 字段，任意角色用户调用该技能
- **THEN** 技能加载器默认 `min_user_level='guest'`，任意角色均可执行

### 5. 多技能编排

LLM 将用户复杂指令分解为多个技能调用。LLM 自主决定调用顺序与数据传递方式，而非依赖硬编码的工作流。编排过程中，LLM 可根据前一个调用的输出动态决定后续步骤。

### 6. 内置技能

系统预装以下三个开箱即用的技能插件：

- **weather** — 天气查询
- **schedule** — 日程管理
- **reminder** — 提醒设置

内置技能遵循与第三方插件相同的目录结构和生命周期。

### 7. 热重载

系统对 `skills/` 目录注册文件监听器。当目录下的 `manifest.json`、`handler.py` 或 `prompt.md` 文件发生新增、修改或删除时，系统自动重新加载受影响的插件，无需重启服务。重新加载过程中，正在执行的任务不受影响，新任务使用更新后的版本。
