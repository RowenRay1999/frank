## MODIFIED Requirements

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
