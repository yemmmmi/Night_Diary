<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { chatCopy } from '@/shared/copy/chat'
import type { SkillSpec, UserSkill } from '@/shared/api/conversation'

const props = defineProps<{
  disabled?: boolean
  skill?: UserSkill | null
  skills?: SkillSpec[]
}>()

const emit = defineEmits<{
  send: [text: string]
  'update:skill': [skill: UserSkill | null]
}>()

const text = ref('')
const fieldEl = ref<HTMLTextAreaElement | null>(null)

const skillCatalog = computed<SkillSpec[]>(() => props.skills ?? [])

/* 未传 / 已复位时都视为「自动」 */
const selectedSkillValue = computed<UserSkill | null>(() => props.skill ?? null)

/* 手动 skill 选择 chips：自动 + 动态技能目录（后端注册表发现） */
const skillOptions = computed(() => [
  { value: null as UserSkill | null, label: chatCopy.skillModeAuto, title: chatCopy.skillModeAutoTitle },
  ...skillCatalog.value.map((spec) => ({
    value: spec.id as UserSkill,
    label: spec.label,
    title: spec.description,
  })),
])

function onSend() {
  const trimmed = text.value.trim()
  if (!trimmed) return
  emit('send', trimmed)
  text.value = ''
}

function onSelectSkill(value: UserSkill | null) {
  emit('update:skill', value)
}

/* ── / 命令菜单：输入 / 唤起技能浮层，↑↓ 导航，Enter/Tab 选中 ── */

const menuActiveIndex = ref(0)

const menuQuery = computed(() => {
  if (!text.value.startsWith('/')) return null
  return text.value.slice(1).split(/\s/, 1)[0] ?? ''
})

const menuOpen = computed(() => menuQuery.value !== null && !props.disabled)

const menuItems = computed<SkillSpec[]>(() => {
  const query = menuQuery.value
  if (query === null) return []
  const needle = query.trim().toLowerCase()
  if (!needle) return skillCatalog.value
  return skillCatalog.value.filter(
    (spec) =>
      spec.label.toLowerCase().includes(needle) ||
      spec.id.toLowerCase().includes(needle) ||
      spec.description.toLowerCase().includes(needle),
  )
})

watch(menuItems, (items) => {
  if (menuActiveIndex.value >= items.length) menuActiveIndex.value = 0
})

function moveMenuSelection(step: number) {
  const count = menuItems.value.length
  if (count === 0) return
  menuActiveIndex.value = (menuActiveIndex.value + step + count) % count
}

function closeMenu() {
  // 关闭即退出 / 前缀：去掉行首命令 token，光标留在原处
  const leading = text.value.match(/^\/\S*\s?/)
  if (leading) text.value = text.value.slice(leading[0].length)
}

function pickMenuItem(spec: SkillSpec) {
  emit('update:skill', spec.id)
  const leading = text.value.match(/^\/\S*\s?/)
  if (leading) text.value = text.value.slice(leading[0].length)
  nextTick(() => fieldEl.value?.focus())
}

function onKeydown(e: KeyboardEvent) {
  if (menuOpen.value) {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      moveMenuSelection(1)
      return
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault()
      moveMenuSelection(-1)
      return
    }
    if ((e.key === 'Enter' || e.key === 'Tab') && menuItems.value.length > 0) {
      e.preventDefault()
      pickMenuItem(menuItems.value[menuActiveIndex.value])
      return
    }
    if (e.key === 'Escape') {
      e.preventDefault()
      closeMenu()
      return
    }
  }
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    onSend()
  }
}

/* 供空态 skill 起手卡调用：填入引导句并聚焦到行尾 */
function prefill(value: string) {
  text.value = value
  nextTick(() => {
    const el = fieldEl.value
    if (!el) return
    el.focus()
    el.setSelectionRange(el.value.length, el.value.length)
  })
}

defineExpose({ prefill })
</script>

<template>
  <div class="letter-composer">
    <div class="letter-composer__skills" data-testid="skill-picker">
      <button
        v-for="option in skillOptions"
        :key="option.value ?? 'auto'"
        type="button"
        class="letter-composer__skill"
        :class="{ 'is-active': selectedSkillValue === option.value }"
        :data-testid="`skill-chip-${option.value ?? 'auto'}`"
        :title="option.title"
        :disabled="disabled"
        @click="onSelectSkill(option.value)"
      >
        {{ option.label }}
      </button>
    </div>
    <div class="letter-composer__row">
      <div class="letter-composer__box" data-testid="letter-input">
        <div v-if="menuOpen" class="letter-composer__menu" data-testid="skill-menu">
          <button
            v-for="(item, index) in menuItems"
            :key="item.id"
            type="button"
            class="letter-composer__menu-item"
            :class="{ 'is-active': index === menuActiveIndex }"
            :data-testid="`skill-menu-item-${item.id}`"
            @mousedown.prevent
            @mouseenter="menuActiveIndex = index"
            @click="pickMenuItem(item)"
          >
            <span class="letter-composer__menu-label">{{ item.label }}</span>
            <span class="letter-composer__menu-desc">{{ item.description }}</span>
          </button>
          <p v-if="menuItems.length === 0" class="letter-composer__menu-empty">
            {{ chatCopy.skillMenuEmpty }}
          </p>
          <p class="letter-composer__menu-hint">{{ chatCopy.skillMenuHint }}</p>
        </div>
        <textarea
          ref="fieldEl"
          v-model="text"
          class="letter-composer__field"
          rows="1"
          :placeholder="chatCopy.inputPlaceholder"
          :disabled="disabled"
          @keydown="onKeydown"
        />
      </div>
      <button
        type="button"
        class="letter-composer__send"
        data-testid="letter-send"
        :disabled="!text.trim() || disabled"
        @click="onSend"
      >
        {{ chatCopy.sendLabel }}
      </button>
    </div>
  </div>
</template>

<style scoped>
/* 圆棱方框回信输入：纸上的一只浅盒，落笔时描边点亮 */
.letter-composer {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.letter-composer__row {
  display: flex;
  align-items: flex-end;
  gap: 0.75rem;
}

/* 手动 skill 选择：药丸底 + 主文字色，选中者反白着墨 */
.letter-composer__skills {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
  padding-left: 0.125rem;
}

.letter-composer__skill {
  padding: 0.25rem 0.75rem;
  border: 1px solid var(--color-border);
  border-radius: 999px;
  background: var(--color-bg-elevated);
  font-size: 0.75rem;
  color: var(--color-text-primary);
  cursor: pointer;
  transition:
    color var(--motion-duration) var(--motion-ease),
    border-color var(--motion-duration) var(--motion-ease),
    background var(--motion-duration) var(--motion-ease);
}

.letter-composer__skill:hover:not(:disabled) {
  border-color: color-mix(in srgb, var(--color-accent) 45%, var(--color-border));
}

/* accent-muted 底上必须配 --color-bg 文字：夜间=墨字压浅底，日间=米字压深底 */
.letter-composer__skill.is-active {
  border-color: color-mix(in srgb, var(--color-accent) 55%, var(--color-border));
  background: var(--color-accent-muted);
  color: var(--color-bg);
  font-weight: 600;
}

.letter-composer__skill:disabled {
  opacity: 0.4;
  cursor: default;
}

.letter-composer__box {
  position: relative;
  flex: 1;
  min-width: 0;
  padding: 0.5rem 0.875rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-inner);
  background: var(--color-bg-elevated);
  transition: border-color var(--motion-duration) var(--motion-ease),
    box-shadow var(--motion-duration) var(--motion-ease);
}

.letter-composer__box:focus-within {
  border-color: color-mix(in srgb, var(--color-accent) 55%, var(--color-border));
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--color-accent) 15%, transparent);
}

/* / 命令菜单：悬于输入盒上方的一页便笺 */
.letter-composer__menu {
  position: absolute;
  bottom: calc(100% + 0.5rem);
  left: 0;
  width: min(20rem, 100%);
  padding: 0.375rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-inner);
  background: var(--color-bg-elevated);
  box-shadow: 0 0.5rem 1.5rem rgba(0, 0, 0, 0.12);
  z-index: 20;
}

.letter-composer__menu-item {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
  width: 100%;
  padding: 0.375rem 0.625rem;
  border: none;
  border-radius: calc(var(--radius-inner) - 0.25rem);
  background: transparent;
  text-align: left;
  cursor: pointer;
}

/* 激活项反白：accent-muted 底配 --color-bg 文字，两主题均高对比 */
.letter-composer__menu-item.is-active {
  background: var(--color-accent-muted);
}

.letter-composer__menu-item.is-active .letter-composer__menu-label,
.letter-composer__menu-item.is-active .letter-composer__menu-desc {
  color: var(--color-bg);
}

.letter-composer__menu-label {
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--color-text-primary);
}

.letter-composer__menu-desc {
  font-size: 0.75rem;
  line-height: 1.5;
  color: var(--color-text-secondary);
}

.letter-composer__menu-empty {
  margin: 0;
  padding: 0.375rem 0.625rem;
  font-size: 0.75rem;
  color: var(--color-text-secondary);
}

.letter-composer__menu-hint {
  margin: 0.25rem 0 0;
  padding: 0.375rem 0.625rem 0.125rem;
  border-top: 1px solid var(--color-border);
  font-size: 0.6875rem;
  letter-spacing: 0.04em;
  color: var(--color-text-secondary);
}

.letter-composer__field {
  display: block;
  width: 100%;
  border: none;
  background: transparent;
  padding: 0;
  color: var(--color-text-primary);
  font-family: var(--font-diary);
  font-size: 0.9375rem;
  line-height: 1.8;
  resize: none;
  outline: none;
}

.letter-composer__field::placeholder {
  color: var(--color-text-faint);
}

.letter-composer__field:disabled {
  opacity: 0.6;
}

.letter-composer__send {
  border: 1px solid var(--color-border);
  background: var(--color-bg-elevated);
  padding: 0.4375rem 0.875rem;
  border-radius: var(--radius-button);
  flex-shrink: 0;
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition:
    border-color var(--motion-duration) var(--motion-ease),
    color var(--motion-duration) var(--motion-ease),
    background var(--motion-duration) var(--motion-ease);
}

.letter-composer__send:hover:not(:disabled) {
  border-color: color-mix(in srgb, var(--color-accent) 45%, var(--color-border));
  color: var(--color-text-primary);
}

.letter-composer__send:disabled {
  opacity: 0.35;
  cursor: default;
}
</style>
