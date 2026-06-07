# 夜记设计 · 参考摘录

> taste-skill 原则摘录 + 场景映射。不适用项标记 **SKIP**。

## 场景 → 组件 / 布局

| 场景 | 布局 archetype | 核心组件 | 备注 |
|------|----------------|----------|------|
| 启动 | 居中 Logo + 能量条 | ParticleBackground, GlassPanel | 无 nav |
| 首页 | 8 列 kanban（7 天 + 收纳箱） | GlassPanel, GameButton | 见参考图片3 |
| 日记 | 全屏信纸 | MoodSelector, GlassPanel | emoji 仅此处 |
| 分析 | 来信卡片 | AITypingIndicator, GameButton | 打字光点 |
| 回顾 | 书架 / 月历 | PageTransition, GlassPanel | 与首页互补 |
| 设置 | 折叠分区 | GlassPanel, GameButton | 非密集表单 |
| Demo | `#/design-system` | 全部 | D-1 验收 |

## taste-skill 适用摘录

### soft-skill · Ethereal Glass（Adapted）

- Double-Bezel：外 `2rem` / 内 `calc(2rem - 6px)`
- 磁吸按钮 hover：scale 1.02 + 阴影抬升
- **偏离**：夜间用 Material 抬升面，非 OLED 纯黑

### taste-skill-v1 · Liquid Glass（Adapted）

- 玻璃：`border` + inset shadow；blur 仅 fixed 层
- 粒子：Canvas mesh / 星尘，禁止 DOM 粒子
- **偏离**：禁止 landing hero、Mac Dock nav → **SKIP**

### redesign-skill 流程

1. **Scan**：现有 Vue + Tailwind + `data-theme`
2. **Diagnose**：对照 DESIGN.md 禁止清单
3. **Fix**：增量改 UI，不破坏 API / 业务逻辑

## SKIP 清单（勿照搬）

| 模式 | 原因 |
|------|------|
| Landing hero 全屏 | 产品场景非营销页 |
| scroll-hijack | 桌面日记应用 |
| Inter 字体 | 项目禁用 |
| AI 紫蓝渐变 | 禁止清单 |
| 三列等宽 SaaS | 禁止清单 |
| 参考图3 暗棕低对比色 | 仅借 kanban 布局 |

## 品牌参考文件

- 白天身份板：`docs/design-assets/night-diary-brandkit-3x3-v2.png`（若已入库）
- 夜间定稿：**B 版「沉稳灰阶」** Material `#121212` 体系
- Kanban 布局：`前端参考图/参考图片3.png`

## 来源注明

- [Leonxlnx/taste-skill](https://github.com/Leonxlnx/taste-skill) — redesign-skill, soft-skill, taste-skill-v1, output-skill（原则摘录，非整文件复制）
- Material Design dark theme — 夜间 elevation
- Linear luminance stacking — 发丝线 + 层级（夜间辅助参考）
