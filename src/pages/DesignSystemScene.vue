<script setup lang="ts">
import { ref } from 'vue'
import { PhMoon, PhSun } from '@phosphor-icons/vue'

import AITypingIndicator from '@/shared/components/AITypingIndicator.vue'
import GameButton from '@/shared/components/GameButton.vue'
import GlassPanel from '@/shared/components/GlassPanel.vue'
import MoodSelector from '@/shared/components/MoodSelector.vue'
import { useTheme } from '@/shared/composables/useTheme'

const { theme, setTheme } = useTheme()

function toggleTheme() {
  setTheme(theme.value === 'day' ? 'night' : 'day')
}
const mood = ref('calm')
</script>

<template>
  <div class="design-system">
    <main class="design-system__main">
      <header class="design-system__header stagger-item">
        <div>
          <h1 class="design-system__title">设计系统</h1>
          <p class="design-system__subtitle">Phase D-1 · 组件预览与主题验收</p>
        </div>
        <GameButton variant="secondary" @click="toggleTheme">
          <PhSun v-if="theme === 'night'" :size="16" weight="duotone" />
          <PhMoon v-else :size="16" weight="duotone" />
          {{ theme === 'day' ? '切换夜间' : '切换白天' }}
        </GameButton>
      </header>

      <div class="design-system__grid">
        <GlassPanel class="stagger-item" elevated>
          <h2 class="section-title">GlassPanel</h2>
          <p class="section-copy">Double-Bezel 容器；夜间 Material 抬升面，白天轻玻璃。</p>
        </GlassPanel>

        <GlassPanel class="stagger-item" blur>
          <h2 class="section-title">GameButton</h2>
          <div class="button-row">
            <GameButton variant="primary">主要按钮</GameButton>
            <GameButton variant="secondary">次要按钮</GameButton>
            <GameButton variant="ghost">幽灵按钮</GameButton>
          </div>
        </GlassPanel>

        <GlassPanel class="stagger-item" elevated>
          <h2 class="section-title">MoodSelector</h2>
          <p class="section-copy">唯一允许 emoji 的场景。</p>
          <MoodSelector v-model="mood" class="mt-4" />
        </GlassPanel>

        <GlassPanel class="stagger-item" elevated>
          <h2 class="section-title">AITypingIndicator</h2>
          <p class="section-copy">组件演示 · 分析场景占位动画（会一直循环，并非卡住）</p>
          <AITypingIndicator class="mt-2" />
        </GlassPanel>

        <GlassPanel class="stagger-item font-diary" elevated :padding="true">
          <h2 class="section-title">日记字体 · 霞鹜文楷</h2>
          <p class="diary-sample">
            今夜的风很轻，我把白天没说完的话，悄悄写进这一页。
          </p>
        </GlassPanel>

        <GlassPanel class="stagger-item" elevated>
          <h2 class="section-title">Kanban 预览（首页布局）</h2>
          <p class="section-copy">周视图 + 收纳箱 · 参考图片3 布局，DESIGN.md 配色。</p>
          <div class="kanban-preview">
            <div v-for="day in ['周一', '周二', '周三', '收纳箱']" :key="day" class="kanban-col">
              <div class="kanban-col__head">{{ day }}</div>
              <div class="kanban-card">😌 今天想早点睡</div>
              <button type="button" class="kanban-add">+</button>
            </div>
          </div>
        </GlassPanel>
      </div>

      <footer class="design-system__footer stagger-item">
        <RouterLink to="/" class="footer-link">返回首页</RouterLink>
      </footer>
    </main>
  </div>
</template>

<style scoped>
.design-system {
  min-height: 100vh;
  position: relative;
}

.design-system__main {
  padding: 1.5rem 1.5rem 2rem;
  max-width: 72rem;
  margin: 0 auto;
}

.design-system__header {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.design-system__title {
  font-size: 1.75rem;
  font-weight: 700;
  color: var(--color-text-primary);
}

.design-system__subtitle {
  margin-top: 0.25rem;
  font-size: 0.875rem;
  color: var(--color-text-secondary);
}

.design-system__grid {
  display: grid;
  gap: 1rem;
}

@media (min-width: 768px) {
  .design-system__grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

.section-title {
  font-size: 1rem;
  font-weight: 600;
  margin-bottom: 0.5rem;
}

.section-copy {
  font-size: 0.875rem;
  color: var(--color-text-secondary);
}

.button-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  margin-top: 0.75rem;
}

.diary-sample {
  font-size: 1.125rem;
  line-height: 1.8;
  color: var(--color-text-primary);
}

.kanban-preview {
  display: flex;
  gap: 0.5rem;
  overflow-x: auto;
  margin-top: 1rem;
  padding-bottom: 0.5rem;
}

.kanban-col {
  min-width: 7rem;
  flex-shrink: 0;
  background: var(--color-bg-elevated-2);
  border: 1px solid var(--color-border);
  border-radius: 0.75rem;
  padding: 0.5rem;
}

.kanban-col__head {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--color-text-secondary);
  margin-bottom: 0.5rem;
  text-align: center;
}

.kanban-card {
  font-size: 0.75rem;
  padding: 0.5rem;
  border-radius: 0.5rem;
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border);
  margin-bottom: 0.5rem;
}

.kanban-add {
  width: 100%;
  border: 1px dashed var(--color-border);
  border-radius: 0.375rem;
  background: transparent;
  color: var(--color-text-secondary);
  padding: 0.25rem;
  cursor: pointer;
}

.design-system__footer {
  margin-top: 2rem;
}

.footer-link {
  font-size: 0.875rem;
  color: var(--color-accent);
  text-decoration: none;
}

.footer-link:hover {
  text-decoration: underline;
}
</style>
