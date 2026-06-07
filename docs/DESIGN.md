# 夜记 · 视觉设计规范

> 审美与施工的唯一来源。Phase D 前端改动须与此文档及 `.cursor/skills/night-diary-design/` 保持一致。

## 1. 产品定位

- **受众**：简体中文用户，单用户本地桌面日记
- **气质**：陪伴型、非社交、非 SaaS 仪表盘
- **文案**：UI 仅使用简体中文（无英文 tagline、无英文占位符）

## 2. 品牌标识

- **名称**：夜记
- **标志**：「N」字母与新月负形 + 折纸路径线（见品牌身份板 B 版），施工时保持造型一致，不做二次 redesign
- **身份板参考**：`docs/design-assets/`（白天奶油版 + 夜间 B 版「沉稳灰阶」）

## 3. 双主题色板

### 3.1 白天 · 暖奶油（Day）

| Token | 值 | 用途 |
|-------|-----|------|
| `--color-bg` | `#EDE6DC` | 页面底色（较 v1 奶油略降亮度） |
| `--color-bg-elevated` | `#F5F0E8` | 卡片 / 列表面 |
| `--color-bg-elevated-2` | `#E8E0D5` | 次级抬升 |
| `--color-text-primary` | `#3D3429` | 正文 |
| `--color-text-secondary` | `#7A6F63` | 次要 / 元信息 |
| `--color-accent` | `#D4A574` | 主强调（CTA、选中） |
| `--color-accent-muted` | `#C4956A` | hover / 降饱和强调 |
| `--color-border` | `rgba(61, 52, 41, 0.10)` | 发丝线 |
| `--glass-bg` | `rgba(255, 255, 255, 0.72)` | 固定层玻璃 |
| `--glass-border` | `rgba(61, 52, 41, 0.12)` | 玻璃描边 |

### 3.2 夜间 · 沉稳灰阶（Night，Material B 定稿）

参考 Material Design 暗色层级 + Day One 日记暗色可读性。**夜 ≠ 装饰性光斑**，用抬升面表达深度，不用紫罗兰 bokeh。

| Token | 值 | 用途 |
|-------|-----|------|
| `--color-bg` | `#121212` | 基面（非纯黑） |
| `--color-bg-elevated` | `#1E1E1E` | 卡片 / kanban 列 |
| `--color-bg-elevated-2` | `#2C2C2C` | 更高抬升 / hover |
| `--color-text-primary` | `#E0E0E0` | 正文 |
| `--color-text-secondary` | `#9E9E9E` | 次要 |
| `--color-accent` | `#C4956A` | 降饱和琥珀强调 |
| `--color-accent-muted` | `#A67B52` | hover |
| `--color-border` | `rgba(255, 255, 255, 0.12)` | 发丝线 |
| `--glass-bg` | `rgba(255, 255, 255, 0.05)` | 固定层（白叠层感） |
| `--glass-border` | `rgba(255, 255, 255, 0.08)` | 玻璃描边 |

### 3.3 语义色（双主题共用）

| Token | 用途 |
|-------|------|
| `--color-success` | 成功 / 已分析 |
| `--color-warning` | 待处理 |
| `--color-danger` | 删除 / 错误 |

## 4. 字体

| 角色 | 字体 | 用途 |
|------|------|------|
| UI | **Plus Jakarta Sans** | 按钮、标签、kanban、设置 |
| 日记展示 | **LXGW WenKai（霞鹜文楷）** | 日记正文预览、信纸区 |

**禁止**：Inter 作为 UI 字体。

## 5. 设计 Dial

| Dial | 值 | 说明 |
|------|-----|------|
| `DESIGN_VARIANCE` | 6 | 产品 UI，略低于 landing 的 8 |
| `MOTION_INTENSITY` | 6 | hover/click 有触感，无 scroll-hijack |
| `VISUAL_DENSITY` | 5 | kanban 可读，非密集表单 |

## 6. 圆角 · Double-Bezel

- 外圆角：`2rem`（32px）
- 内圆角：`calc(2rem - 6px)`
- 按钮 / chip：`0.75rem` ~ `1rem`

## 7. 禁止清单

- AI 紫蓝渐变、三列等宽 SaaS 卡片
- Inter 字体
- 英文 UI 文案
- 滚动容器上的 `backdrop-blur`（仅 fixed 标题栏 / GlassPanel 外壳）
- DOM 粒子（须 Canvas）
- 除 `MoodSelector` 外使用 emoji（其余用 Phosphor 图标）
- 夜间主题的装饰性 bokeh / 品红光斑 / 摩天轮式氛围图

## 8. Tauri 性能护栏

- 粒子：`ParticleBackground` 使用 Canvas + `requestAnimationFrame`
- `backdrop-blur`：仅用于 `CustomTitlebar`、`GlassPanel` 外壳等 fixed 层
- 路由切换：优先 CSS + Vue `<Transition>`；GSAP 仅用于 `PageTransition` 编排

## 9. 场景 → 布局映射

| 场景 | 布局原型 | 参考 |
|------|----------|------|
| 启动 | Logo + 能量条进度 + 粒子 | 品牌板 Panel 3 变体 |
| **首页 / 日记管理** | **周视图 kanban：周一～周日 + 收纳箱** | `前端参考图/参考图片3.png`（借布局，不借其暗棕低对比配色） |
| 日记写作 | 全屏羊皮纸 / 信纸 + MoodSelector | 品牌板白天版 |
| AI 分析 | 来信样式 + AITypingIndicator | — |
| 回顾 | 月历 / 书架时间线 | 与 weekly kanban 互补 |
| 设置 | 分区折叠面板，非密集表单 | Material 抬升卡片 |

### Kanban 卡片语义（非任务管理）

- 去掉任务勾选 → **情绪 emoji + 摘要一行**
- 状态 chip：`已有回信` / `待分析` / `续写`
- 列底 `[+]` → 当天新建日记
- 顶栏：`‹ 上周` · `YYYY年M月D日 - M月D日` · `下周 ›`

## 10. 组件库（D-1）

| 组件 | 职责 |
|------|------|
| `GlassPanel` | Double-Bezel 容器；夜间用抬升面，白天轻玻璃 |
| `GameButton` | 磁吸 hover + 涟漪 click；primary / secondary / ghost |
| `ParticleBackground` | Canvas 环境粒子（日：暖尘；夜：稀疏星点） |
| `PageTransition` | 路由级 stagger 进出场 |
| `AITypingIndicator` | 三光点脉动 +「正在思考…」 |
| `MoodSelector` | emoji 网格（唯一允许 emoji 的场景） |
| `CustomTitlebar` | 无 decorations 窗口：拖拽 + 最小化 / 最大化 / 关闭 |

## 11. 主题切换

- HTML 根节点：`data-theme="day" | "night"`
- 默认跟随 `prefers-color-scheme`，用户选择持久化到 `localStorage`（key: `night-diary-theme`）
- 样式文件：`src/styles/themes/day.css` / `night.css`

## 12. 场景构图参考

完整场景 mock 以品牌身份板 + `前端参考图/参考图片3.png` 为准；施工阶段见 `#/design-system` demo 页。
