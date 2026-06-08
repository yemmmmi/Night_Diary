---
name: night-diary-design
description: >-
  夜记 Phase D 游戏化 UI 施工规范。修改 src/shared/components/、src/styles/、*Scene.vue
  或实现 GlassPanel/GameButton/ParticleBackground 等设计系统组件时使用。遵循 docs/DESIGN.md
  双主题（白天奶油 + 夜间 Material B 沉稳灰阶）、中文-only、kanban 首页布局。
---

# 夜记设计系统 Skill

## 触发条件

- Phase D 前端施工
- 修改 `src/shared/components/`、`src/styles/`、任意 `*Scene.vue`
- 用户提及「设计系统」「主题」「游戏化 UI」「kanban」

## 施工前必读

1. `docs/DESIGN.md`
2. 本目录 `tokens.md`（CSS 变量）
3. `reference.md`（场景映射 + SKIP 清单）

## 执行协议（redesign + soft）

1. **Scan**：现有 Vue 3 SFC + Tailwind + `data-theme`
2. **Diagnose**：对照 DESIGN.md §7 禁止清单
3. **Fix**：增量改 UI，**不破坏** API / 业务逻辑 / 路由契约

## 栈适配（强制）

| 项 | 规则 |
|----|------|
| 框架 | Vue 3 SFC + Tailwind v3 |
| 主题 | `data-theme="day"\|"night"` on `<html>` |
| 动效 | CSS transition 默认；GSAP 仅 `PageTransition` 编排 |
| 图标 | `@phosphor-icons/vue`；**UI 禁止 emoji** |
| 文案 | **仅简体中文** |
| 字体 | Plus Jakarta Sans（UI）+ LXGW WenKai（日记）— **禁止 Inter** |

## 双主题定稿

- **白天**：暖奶油 `#FDF8F3`，琥珀 `#D4A574`
- **夜间**：Material B「沉稳灰阶」`#121212` / `#1E1E1E` / `#2C2C2C`，琥珀 `#C4956A`
- **标志**：「N」新月折纸 monogram — 不 redesign
- **夜间禁止**：紫罗兰 bokeh、品红光斑、装饰性氛围噪音

## 组件指引

| 组件 | 实现要点 |
|------|----------|
| `GlassPanel` | Double-Bezel；夜间抬升面为主，blur 仅 fixed 外壳 |
| `GameButton` | 磁吸 hover + ripple click；primary/secondary/ghost |
| `ParticleBackground` | Canvas；日=暖尘，夜=稀疏星点（低噪音） |
| `PageTransition` | stagger entry；非 scroll-hijack |
| `AITypingIndicator` | 三光点 perpetual pulse |
| ~~`MoodSelector`~~ | **已废弃** — 不提供用户自选心情 emoji |
| `CustomTitlebar` | `data-tauri-drag-region` + 窗口控制 |

## 首页布局（D-2 预埋）

HomeScene 核心：**周视图 kanban**（周一～周日 + 收纳箱），布局参考 `前端参考图/参考图片3.png`，配色用 DESIGN.md token（不借参考图暗棕色）。卡片仅摘要一行 + 状态 chip，无 emoji。

DiaryScene：**方案 A 中性书写面**（`--color-diary-surface`），霞鹜文楷正文；不用暖黄羊皮纸、不用心情 emoji；写作页粒子减弱/关闭。

## output-skill 约束

- 禁止 `// ...` 占位
- 禁止「如需继续请告知」
- 多文件组件须完整输出

## Pre-flight Checklist

- [ ] 中文-only UI 文案
- [ ] 无 Inter / 无 AI 紫蓝渐变
- [ ] 滚动区无 backdrop-blur
- [ ] 粒子为 Canvas
- [ ] 夜间用 elevation 层级，非纯黑 / 非光斑噪音
- [ ] `vue-tsc --noEmit` 零错误
