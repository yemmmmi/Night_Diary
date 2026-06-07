# 夜记设计 Token（施工只读）

同步自 `docs/DESIGN.md`。修改 token 时先改 DESIGN.md，再更新本文件与 `src/styles/`。

## 白天 theme `[data-theme="day"]`

```css
--color-bg: #EDE6DC;
--color-bg-elevated: #F5F0E8;
--color-bg-elevated-2: #E8E0D5;
--color-text-primary: #3D3429;
--color-text-secondary: #7A6F63;
--color-accent: #D4A574;
--color-accent-muted: #C4956A;
--color-border: rgba(61, 52, 41, 0.10);
--glass-bg: rgba(255, 255, 255, 0.72);
--glass-border: rgba(61, 52, 41, 0.12);
--color-success: #5a8f6a;
--color-warning: #c49a3c;
--color-danger: #b85450;
--radius-outer: 2rem;
--radius-inner: calc(2rem - 6px);
--radius-button: 0.875rem;
--font-ui: "Plus Jakarta Sans", "PingFang SC", "Microsoft YaHei", sans-serif;
--font-diary: "LXGW WenKai", "KaiTi", serif;
--motion-duration: 220ms;
--motion-ease: cubic-bezier(0.22, 1, 0.36, 1);
```

## 夜间 theme `[data-theme="night"]`

```css
--color-bg: #121212;
--color-bg-elevated: #1E1E1E;
--color-bg-elevated-2: #2C2C2C;
--color-text-primary: #E0E0E0;
--color-text-secondary: #9E9E9E;
--color-accent: #C4956A;
--color-accent-muted: #A67B52;
--color-border: rgba(255, 255, 255, 0.12);
--glass-bg: rgba(255, 255, 255, 0.05);
--glass-border: rgba(255, 255, 255, 0.08);
--color-success: #6aaf7a;
--color-warning: #d4a84a;
--color-danger: #cf6679;
```

## Dial

- DESIGN_VARIANCE: 6
- MOTION_INTENSITY: 6
- VISUAL_DENSITY: 5
