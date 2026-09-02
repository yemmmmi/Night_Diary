# PR6 计划：前端视觉打磨 — 字体落地 + 组件统一 + 空态节奏

## 背景

PR1-PR5 完成结构重构后，用户反馈「不如预期」。诊断发现三个根因：

1. **字体全部落空**：base.css 注释明确写「系统字体回退」，Noto Serif SC / 霞鹜文楷 / Plus Jakarta Sans 均未加载，Windows 上实际渲染为 SimSun / 微软雅黑 / KaiTi。纸感设计的灵魂是字体，字体落空 = 设计落空。
2. **新旧设计语言混搭**：GameButton primary 仍是黛蓝实心大按钮（旧 v2 语言），TimelineScene 切换器是胶囊+阴影，DayView 仍用 GlassPanel 圆角卡片，情绪色硬编码彩虹值。
3. **空态粗糙**：三种随意形态（一行小字/虚线大卡/完全空白），页面内容堆上半屏、下方大片空白。

## 范围

P0（字体落地）+ P1（组件统一）+ P2（空态节奏），一个 PR 收口。

## 改动清单

### Task 1 字体自托管
- [x] 安装 @fontsource/noto-serif-sc (400/600/700 chinese-simplified)、@fontsource/plus-jakarta-sans、lxgw-wenkai-webfont (regular/bold)
- [x] main.ts 中以 JS import 加载（Vite 正确打包）
- [x] base.css 移除占位注释，更新说明

### Task 2 按钮语言
- [x] GameButton：padding 收紧至 0.375rem 0.875rem、圆角 3px、字号 0.8125rem（小号实心黛蓝，每页唯一焦点）
- [x] secondary 改为透明底 + 细线边框

### Task 3 记录页
- [x] 切换器：去胶囊/阴影，改为底线 tab（2px accent 底线生长）
- [x] DayView：去 GlassPanel，改为细线行（上下 1px 分隔）
- [x] 空态：去虚线大卡片，改为居中衬线标题 + 淡墨辅助 + 主 CTA
- [x] 情绪色：去硬编码彩虹值，统一为 seal token（--color-seal-positive/calm/lost/muted）
- [x] 「今天」tag：去实心黛蓝底，改为 accent 细线框

### Task 4 今天页
- [x] 大日期：2.125rem → 2.75rem，行高收紧
- [x] 日期区 margin-bottom 加大至 2.5rem
- [x] 空态：改为居中衬线标题「这一页还是空白」+ 辅助「从一句话开始就好」+ primary CTA

### Task 5 规划页
- [x] 标题：font-ui 1.25rem → font-display 1.5rem
- [x] 空态：居中 + 衬线标题

### Task 6 洞悉页
- [x] 主标题：1.25rem → 1.75rem
- [x] 去重复：概览区「长期画像尚未建立」仅在 profile_built 时显示文案，未建立时不再重复出现（下方已有独立区块展示）

### Task 7 笔谈页
- [x] 聊天区空态：衬线标题 1.25rem + 限宽居中描述 + 主 CTA（另起一封改为实心黛蓝小按钮）
- [x] 侧栏会话列表：去灰色块选中态，改为左侧 2px accent 竖线指示

## 测试

- [x] vitest 全量通过
- [x] vue-tsc 通过
- [x] npm run build 通过
- [ ] 浏览器验证五页面渲染（字体生效、按钮统一、空态一致）

## 风险

- 字体包体积：noto-serif-sc chinese-simplified 分片 + lxgw-wenkai-webfont 分片，首屏按需加载，总下载量可控（每片约 10-30KB）
- GameButton 尺寸收紧后，所有引用处视觉变小，属预期行为
