## ADDED Requirements

### Requirement: 光球基础渲染

系统 SHALL 在 Zone 2 的 `.monitor-thinking` 区域中央渲染一个名为 ".orb" 的圆形元素，尺寸 88×88px。光球 SHALL 使用 `radial-gradient` 渲染 5 个等宽（各 20% 半径）的同心色阶环，从中心暖白（`oklch(98% 0.005 80)`）向外逐级过渡至深橙（`oklch(52% 0.20 38)`），环之间硬边紧靠，无间隙。

光球 SHALL 具有以下静态样式：
- 边框：2px solid `oklch(62% 0.18 48 / 35%)`
- 外发光：`0 0 60px oklch(58% 0.18 42 / 20%)` + `0 0 120px oklch(52% 0.16 38 / 10%)`
- 内发光：`inset 0 0 28px oklch(60% 0.16 45 / 12%)`

#### Scenario: 光球渲染 5 个色阶同心环

- **WHEN** 主面板首次渲染
- **THEN** Zone 2 上部中央显示 88px 圆形光球，从中心白色到外层深橙色的 5 级色阶清晰可见

#### Scenario: 光球静态发光

- **WHEN** 系统处于 Idle 或 Auth 状态
- **THEN** 光球显示默认外发光和内发光效果，无动画（或仅呼吸动画）

### Requirement: 光球呼吸动画（idle 态）

当系统处于非对话状态（Idle / Auth）时，光球 SHALL 播放 `orb-breathe-rings` 动画：`background-size` 在 100% 到 106% 之间周期变化（周期 3.2s，ease-in-out），使色阶环产生由内向外扩散再收缩的视觉效果。

#### Scenario: 待机时光球呼吸

- **WHEN** 系统处于 Idle 状态
- **THEN** 光球的 background-size 在 100%→106%→100% 之间周期性变化，周期约 3.2 秒

### Requirement: 光球思考动画（thinking 态）

当系统进入对话/思考状态（Chat / Transcribing / Thinking）时，光球 SHALL 同时播放两套动画：
1. **orb-think**：`transform: scale(1) → scale(1.04) → scale(0.97) → scale(1)`，周期 1.8s，ease-in-out
2. **orb-breathe-rings**：周期压缩至 2.4s

思考态下，光球边框颜色 SHALL 切换为 `oklch(68% 0.22 55 / 55%)`，外发光强度 SHALL 增强（80px / 160px blur）。

#### Scenario: 对话中光球播放思考动画

- **WHEN** 系统进入 Chat 状态
- **THEN** 光球同时播放 scale 波动动画和呼吸动画，边框和外发光增亮

#### Scenario: 对话结束光球恢复待机

- **WHEN** 系统从 Chat 状态退出至 Idle 或 Auth
- **THEN** 光球停止 thinking 动画，恢复仅呼吸动画（3.2s 周期），光标和外发光恢复默认强度

### Requirement: 思考扩散光环

光球外围 SHALL 渲染 3 个同心扩散光环元素（`.thinking-ring`），仅在系统处于思考态时可见。光环从光球边缘向外部扩散：`transform: scale(0.75) → scale(1.6)`，同时 `opacity: 0.55 → 0`，周期 2.4s，ease-out。3 个光环 SHALL 分别延迟 0s、0.8s、1.6s 启动，形成连续波纹效果。

#### Scenario: 思考时光环扩散

- **WHEN** 光球进入思考态
- **THEN** 光球外围出现 3 个同心光环，以交错延迟向外扩散并逐渐透明消失，无限循环

#### Scenario: 非思考时光环隐藏

- **WHEN** 光球退出思考态
- **THEN** 所有光环停止动画并隐藏

### Requirement: 悬浮粒子场

光球外围 SHALL 渲染 8 个悬浮粒子元素（`.particle`），尺寸 3×3px，分布在光球周围约 160px 范围内。粒子 SHALL 播放 `particle-float` 动画：从初始位置向 `--dy` 方向（-18px 至 -30px）移动，同时 `opacity: 0 → 0.7 → 0` 和 `scale: 1 → 1.8`，周期 3s，ease-in-out。偶数粒子使用较深橙色（`oklch(58% 0.18 42)`），奇数粒子使用较亮橙色（`oklch(66% 0.22 52)`）。

#### Scenario: 粒子围绕光球漂浮

- **WHEN** 主面板渲染
- **THEN** 8 个彩色粒子在光球周围以不同的延迟和方向循环浮动

### Requirement: 光球悬停与点击交互

光球 SHALL 响应悬停和点击交互：
- 悬停（`:hover`）：`transform: scale(1.06)`，发光增强
- 按下（`:active`）：`transform: scale(0.95)`
- 点击：打开 Chat Overlay 对话浮层

光球 SHALL 设置 `cursor: pointer` 和 `title` 属性提示"点击与 Frank 对话"。

#### Scenario: 鼠标悬停光球

- **WHEN** 用户鼠标悬停在光球上
- **THEN** 光球放大至 1.06 倍，外发光增强

#### Scenario: 点击光球打开对话

- **WHEN** 用户点击光球
- **THEN** Chat Overlay 从右侧滑入，覆盖 Zone 2

### Requirement: 代理状态标签

光球下方 SHALL 显示一个状态标签（`.agent-label`），以等宽字体（`var(--font-mono)`）显示当前代理状态文本（如"聆听中 · 等待唤醒"），左侧带有一个脉冲圆点（橙色，`oklch(68% 0.22 55)`，opacity 在 0.25 到 1 之间脉冲，周期 1.2s）。

标签文本 SHALL 随系统状态机变化：
- Idle/Auth → "聆听中 · 等待唤醒"
- Chat → "对话中 · 正在响应"
- Thinking → "思考中 · 分析中"

#### Scenario: 待机状态显示"等待唤醒"

- **WHEN** 系统处于 Idle 或 Auth 状态
- **THEN** 状态标签显示 "聆听中 · 等待唤醒"，左侧橙色圆点脉冲

#### Scenario: 对话状态显示"对话中"

- **WHEN** 系统进入 Chat 状态
- **THEN** 状态标签切换为 "对话中 · 正在响应"
