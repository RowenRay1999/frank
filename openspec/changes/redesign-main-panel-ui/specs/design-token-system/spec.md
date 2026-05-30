## ADDED Requirements

### Requirement: CSS 变量驱动设计令牌

系统 SHALL 在 `:root` 中定义完整的设计令牌（Design Tokens）作为 CSS 自定义属性，分为原始值（Primitives）和语义令牌（Semantic）两层。所有视觉样式 SHALL 通过引用这些变量实现，避免硬编码色值、间距、圆角或动效参数。

#### Scenario: 所有视觉属性使用 CSS 变量

- **WHEN** 审查 styles.css 中的视觉属性（color, background, border, padding, margin, border-radius, transition, font-family, font-size）
- **THEN** 至少 90% 的视觉属性值引用 CSS 变量而非硬编码值

### Requirement: 色彩令牌

系统 SHALL 定义以下色彩令牌：

**原始色值（Primitives — oklch 色彩空间）**：
| 变量名 | 色值 |
|---|---|
| `--orange-100` | `oklch(98% 0.005 80)` |
| `--orange-200` | `oklch(88% 0.06 65)` |
| `--orange-300` | `oklch(76% 0.12 55)` |
| `--orange-400` | `oklch(64% 0.18 48)` |
| `--orange-500` | `oklch(52% 0.20 38)` |

**语义令牌（Semantic Tokens）**：
| 变量名 | 色值 | 用途 |
|---|---|---|
| `--bg` | `#0a0a0c` | 窗口背景 |
| `--surface-glass` | `rgba(22, 22, 24, 0.75)` | 毛玻璃面板背景 |
| `--surface-elevated` | `rgba(29, 29, 31, 0.85)` | 悬浮面板背景 |
| `--fg` | `#f5f5f7` | 主文字色 |
| `--fg-2` | `#98989d` | 次要文字色 |
| `--muted` | `#636366` | 暗色文字 |
| `--accent` | `oklch(64% 0.18 48)` | 主强调色（暖橙） |
| `--accent-soft` | `rgba(255, 149, 0, 0.12)` | 弱强调色背景 |
| `--accent-hover` | `oklch(58% 0.20 42)` | 强调色悬停 |
| `--accent-on` | `#ffffff` | 强调色上的文字 |
| `--border` | `rgba(255, 255, 255, 0.08)` | 边框 |
| `--border-soft` | `rgba(255, 255, 255, 0.05)` | 弱边框 |
| `--info` | `rgb(100, 210, 255)` | 信息/进行中色 |
| `--success` | `rgb(48, 209, 88)` | 成功色 |
| `--danger` | `rgb(255, 69, 58)` | 危险/错误色 |

#### Scenario: 主文字色为浅色

- **WHEN** 任何文本元素渲染
- **THEN** 主文字色应为 `#f5f5f7`（`var(--fg)` 变量值）

#### Scenario: 强调元素使用暖橙色

- **WHEN** 渲染激活态导航项、发送按钮、Orb 光球
- **THEN** 使用 `var(--accent)` 即 `oklch(64% 0.18 48)` 暖橙色

### Requirement: 间距刻度令牌

系统 SHALL 定义 5 级间距刻度：
| 变量名 | 值 | 用途 |
|---|---|---|
| `--space-1` | `4px` | 元素内部紧贴间距 |
| `--space-2` | `8px` | 相关元素间距 |
| `--space-3` | `12px` | 组件内边距 |
| `--space-4` | `16px` | 区块内边距 |
| `--space-5` | `20px` | 大区块间距 |

#### Scenario: 导航栏内边距使用 space-2 + space-4

- **WHEN** 导航栏渲染
- **THEN** padding 为 `var(--space-2) var(--space-4)` 即 8px 20px

### Requirement: 字体令牌

系统 SHALL 定义以下字体令牌：
| 变量名 | 值 | 用途 |
|---|---|---|
| `--font-display` | `'SF Pro Display', 'Segoe UI', sans-serif` | 展示性文本（标题、名称） |
| `--font-mono` | `'SF Mono', 'Consolas', monospace` | 等宽文本（时间、状态、代码） |
| `--text-xs` | `11px` | 辅助文本（标签、角色、元信息） |
| `--text-sm` | `13px` | 正文（消息、描述） |
| `--text-md` | `16px` | 标题 |

#### Scenario: 时间戳使用等宽字体

- **WHEN** 渲染实时时钟和任务耗时
- **THEN** 字体为 `var(--font-mono)` 等宽字体家族

### Requirement: 圆角令牌

系统 SHALL 定义 4 级圆角：
| 变量名 | 值 | 用途 |
|---|---|---|
| `--radius-sm` | `6px` | 小型元素（任务行、气泡尖角） |
| `--radius-md` | `12px` | 中型元素（导航项、卡片） |
| `--radius-lg` | `18px` | 大型元素（消息气泡） |
| `--radius-full` | `9999px` | 药丸形元素（芯片、标签、按钮） |

#### Scenario: 硬件芯片为药丸形

- **WHEN** 渲染 CAM/MIC/SCR 硬件状态芯片
- **THEN** border-radius 为 `var(--radius-full)` 即 9999px

### Requirement: 动效令牌

系统 SHALL 定义动效持续时间与缓动函数令牌：
| 变量名 | 值 | 用途 |
|---|---|---|
| `--motion-fast` | `150ms` | 微交互（hover、toggle） |
| `--motion-base` | `250ms` | 标准过渡（面板切换） |
| `--motion-slow` | `400ms` | 大型动画（Overlay 滑入、Orb 呼吸） |
| `--ease-standard` | `cubic-bezier(0.2, 0, 0, 1)` | 标准缓出曲线 |

#### Scenario: 按钮悬停使用 fast 动效

- **WHEN** 鼠标悬停在导航项或按钮上
- **THEN** 样式过渡使用 `var(--motion-fast)` 即 150ms

### Requirement: 毛玻璃效果一致性

所有半透明面板（Zone 1 状态栏、Zone 2 任务列表区、Zone 3 导航栏、Chat Overlay）SHALL 使用统一的毛玻璃效果：
- `backdrop-filter: blur(20px)`（Zone 1、Zone 3）
- `backdrop-filter: blur(12px)`（Zone 2 任务列表）
- `backdrop-filter: blur(28px)`（Chat Overlay）
- 同时提供 `-webkit-backdrop-filter` 前缀

#### Scenario: Zone 1 状态栏毛玻璃

- **WHEN** Zone 2 内容在状态栏下方滚动
- **THEN** Zone 1 显示 20px 毛玻璃模糊效果，背景内容被柔化
