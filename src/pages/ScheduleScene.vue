<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { PhArrowLeft } from '@phosphor-icons/vue'

import GameButton from '@/shared/components/GameButton.vue'
import { scheduleCopy as copy } from '@/shared/copy/schedule'
import type { ScheduledTask, ScheduledTaskCreate } from '@/shared/api/schedule'
import { useScheduleStore } from '@/stores/schedule'

defineOptions({ name: 'ScheduleScene' })

const store = useScheduleStore()

const draft = reactive({
  kind: '',
  mode: '',
  cron: '',
  enabled: true,
})

const editingId = ref<string | null>(null)
const editCron = ref('')
const expanded = ref<Set<string>>(new Set())
const showDeleteConfirm = ref(false)
const pendingDeleteId = ref<string | null>(null)

const canCreate = computed(() => draft.kind.length > 0 && draft.cron.trim().length > 0)

const selectedKind = computed(() => store.kinds.find((k) => k.kind === draft.kind) ?? null)
const availableModes = computed(() => selectedKind.value?.allowed_modes ?? [])

function onKindChange(): void {
  draft.mode = selectedKind.value?.default_mode ?? ''
}

function kindLabel(task: ScheduledTask): string {
  return task.kind_label || copy.kinds[task.kind] || task.kind
}

function modeLabel(task: ScheduledTask): string {
  return task.mode_label || copy.modes[task.mode] || task.mode
}

function formatTime(iso: string | null): string {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function statusLabel(status: string | null): string {
  if (status === 'done') return copy.statusDone
  if (status === 'failed') return copy.statusFailed
  if (status === 'running') return copy.statusRunning
  return status ?? ''
}

async function onCreate(): Promise<void> {
  if (!canCreate.value) return
  try {
    const body: ScheduledTaskCreate = {
      kind: draft.kind,
      cron_expr: draft.cron.trim(),
      enabled: draft.enabled,
    }
    if (draft.mode && availableModes.value.length > 1) body.mode = draft.mode
    await store.create(body)
    draft.cron = ''
  } catch {
    // surfaced via store.error
  }
}

async function onToggle(task: ScheduledTask): Promise<void> {
  try {
    await store.update(task.id, { enabled: !task.enabled })
  } catch {
    // surfaced via store.error
  }
}

async function onTrigger(task: ScheduledTask): Promise<void> {
  try {
    await store.trigger(task.id)
    if (expanded.value.has(task.id)) await store.loadRuns(task.id)
  } catch {
    // surfaced via store.error
  }
}

function startEdit(task: ScheduledTask): void {
  editingId.value = task.id
  editCron.value = task.cron_expr
}

async function onSaveEdit(task: ScheduledTask): Promise<void> {
  const cron = editCron.value.trim()
  if (!cron) return
  try {
    await store.update(task.id, { cron_expr: cron })
    editingId.value = null
  } catch {
    // surfaced via store.error
  }
}

function askDelete(id: string): void {
  pendingDeleteId.value = id
  showDeleteConfirm.value = true
}

async function onDeleteConfirm(): Promise<void> {
  const id = pendingDeleteId.value
  showDeleteConfirm.value = false
  pendingDeleteId.value = null
  if (!id) return
  try {
    await store.remove(id)
  } catch {
    // surfaced via store.error
  }
}

async function toggleRuns(task: ScheduledTask): Promise<void> {
  const next = new Set(expanded.value)
  if (next.has(task.id)) {
    next.delete(task.id)
    expanded.value = next
    return
  }
  next.add(task.id)
  expanded.value = next
  try {
    await store.loadRuns(task.id)
  } catch {
    // surfaced via store.error
  }
}

onMounted(async () => {
  try {
    await store.loadAll()
  } catch {
    // surfaced via store.error
  }
  if (!draft.kind && store.kinds.length) draft.kind = store.kinds[0].kind
  onKindChange()
})
</script>

<template>
  <main class="schedule-scene">
    <div class="schedule-scene__container">
      <header class="schedule-scene__header">
        <RouterLink to="/settings" class="schedule-scene__back">
          <PhArrowLeft :size="16" />
          {{ copy.back }}
        </RouterLink>
        <div class="schedule-scene__title-area">
          <h1 class="schedule-scene__title">{{ copy.title }}</h1>
          <p class="schedule-scene__subtitle">{{ copy.subtitle }}</p>
        </div>
      </header>

      <p v-if="store.error" class="schedule-error" role="alert">{{ store.error }}</p>

      <!-- ── 新建 ─────────────────────────────────────────────── -->
      <section class="schedule-card">
        <h2 class="schedule-card__title">{{ copy.createTitle }}</h2>
        <form class="schedule-form" @submit.prevent="onCreate">
          <label class="schedule-field">
            <span class="schedule-field__label">{{ copy.kindLabel }}</span>
            <select
              v-model="draft.kind"
              class="schedule-field__input"
              data-testid="schedule-kind"
              @change="onKindChange"
            >
              <option v-for="k in store.kinds" :key="k.kind" :value="k.kind">
                {{ k.label }}
              </option>
            </select>
          </label>

          <label v-if="availableModes.length > 1" class="schedule-field">
            <span class="schedule-field__label">{{ copy.modeLabel }}</span>
            <select
              v-model="draft.mode"
              class="schedule-field__input"
              data-testid="schedule-mode"
            >
              <option v-for="m in availableModes" :key="m" :value="m">
                {{ copy.modes[m] || m }}
              </option>
            </select>
            <span class="schedule-field__hint">{{ copy.modeHint }}</span>
          </label>

          <label class="schedule-field">
            <span class="schedule-field__label">{{ copy.cronLabel }}</span>
            <input
              v-model="draft.cron"
              class="schedule-field__input"
              :placeholder="copy.cronPlaceholder"
              data-testid="schedule-cron"
            />
            <span class="schedule-field__hint">{{ copy.cronHint }}</span>
          </label>

          <label class="schedule-field schedule-field--checkbox">
            <input v-model="draft.enabled" type="checkbox" data-testid="schedule-enabled" />
            <span>{{ copy.enabledLabel }}</span>
          </label>

          <GameButton
            type="submit"
            :disabled="store.saving || !canCreate"
            data-testid="schedule-create"
          >
            {{ store.saving ? copy.creating : copy.create }}
          </GameButton>
        </form>
      </section>

      <!-- ── 列表 ─────────────────────────────────────────────── -->
      <section class="schedule-card">
        <h2 class="schedule-card__title">{{ copy.listTitle }}</h2>

        <p v-if="!store.tasks.length" class="schedule-empty">
          {{ copy.empty }}
          <span class="schedule-empty__hint">{{ copy.emptyHint }}</span>
        </p>

        <ul class="schedule-list">
          <li
            v-for="task in store.tasks"
            :key="task.id"
            class="schedule-item"
            data-testid="schedule-item"
          >
            <div class="schedule-item__head">
              <span class="schedule-item__kind">{{ kindLabel(task) }}</span>
              <code class="schedule-item__cron">{{ task.cron_expr }}</code>
              <span class="schedule-item__mode" data-testid="schedule-mode-badge">
                {{ modeLabel(task) }}
              </span>
              <span class="schedule-item__badge" :class="{ 'is-off': !task.enabled }">
                {{ task.enabled ? copy.resume : copy.pause }}
              </span>
            </div>

            <div class="schedule-item__meta">
              <span>{{ copy.nextRun }}：{{ formatTime(task.next_run_at) || copy.never }}</span>
              <span>{{ copy.lastRun }}：{{ formatTime(task.last_run_at) || copy.never }}</span>
              <span v-if="task.last_status">{{ statusLabel(task.last_status) }}</span>
            </div>

            <div class="schedule-item__actions">
              <button
                type="button"
                class="schedule-btn"
                data-testid="schedule-toggle"
                :disabled="store.saving"
                @click="onToggle(task)"
              >
                {{ task.enabled ? copy.pause : copy.resume }}
              </button>
              <button
                type="button"
                class="schedule-btn"
                data-testid="schedule-trigger"
                :disabled="store.saving"
                @click="onTrigger(task)"
              >
                {{ store.saving ? copy.running : copy.trigger }}
              </button>
              <button
                type="button"
                class="schedule-btn"
                data-testid="schedule-edit"
                @click="startEdit(task)"
              >
                {{ copy.edit }}
              </button>
              <button
                type="button"
                class="schedule-btn schedule-btn--danger"
                data-testid="schedule-delete"
                @click="askDelete(task.id)"
              >
                {{ copy.delete }}
              </button>
            </div>

            <div v-if="editingId === task.id" class="schedule-edit">
              <input
                v-model="editCron"
                class="schedule-field__input"
                data-testid="schedule-edit-cron"
              />
              <button
                type="button"
                class="schedule-btn"
                data-testid="schedule-save-edit"
                :disabled="store.saving"
                @click="onSaveEdit(task)"
              >
                {{ copy.save }}
              </button>
              <button type="button" class="schedule-btn" @click="editingId = null">
                {{ copy.cancel }}
              </button>
            </div>

            <div class="schedule-runs">
              <button
                type="button"
                class="schedule-btn schedule-btn--ghost"
                data-testid="schedule-runs-toggle"
                @click="toggleRuns(task)"
              >
                {{ expanded.has(task.id) ? copy.hideRuns : copy.runs }}
              </button>
              <ul v-if="expanded.has(task.id)" class="schedule-runs__list">
                <li v-if="!store.runs[task.id]?.length" class="schedule-runs__empty">
                  {{ copy.runsEmpty }}
                </li>
                <li
                  v-for="run in store.runs[task.id]"
                  :key="run.id"
                  class="schedule-runs__item"
                  data-testid="schedule-run"
                >
                  <span class="schedule-runs__time">{{ formatTime(run.started_at) }}</span>
                  <span class="schedule-runs__status">{{ statusLabel(run.status) }}</span>
                  <span class="schedule-runs__text">{{ run.summary || run.error || '' }}</span>
                </li>
              </ul>
            </div>
          </li>
        </ul>
      </section>
    </div>

    <div
      v-if="showDeleteConfirm"
      class="schedule-confirm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="schedule-confirm-title"
    >
      <div class="schedule-confirm__card">
        <p id="schedule-confirm-title" class="schedule-confirm__title">
          {{ copy.confirmDeleteTitle }}
        </p>
        <p class="schedule-confirm__desc">{{ copy.confirmDeleteDesc }}</p>
        <div class="schedule-confirm__actions">
          <GameButton
            variant="secondary"
            data-testid="schedule-delete-cancel"
            @click="showDeleteConfirm = false"
          >
            {{ copy.cancel }}
          </GameButton>
          <GameButton data-testid="schedule-delete-confirm" @click="onDeleteConfirm">
            {{ copy.confirmDelete }}
          </GameButton>
        </div>
      </div>
    </div>
  </main>
</template>

<style scoped>
.schedule-scene {
  min-height: calc(100vh - 2.5rem);
  padding: 1.25rem 1rem 2rem;
}

.schedule-scene__container {
  max-width: 42rem;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.schedule-scene__header {
  display: flex;
  align-items: flex-start;
  gap: 0.875rem;
}

.schedule-scene__back {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  margin-top: 0.25rem;
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
  text-decoration: none;
  transition: color var(--dur-fast) var(--ease-out-quart);
}

.schedule-scene__back:hover {
  color: var(--color-text-primary);
}

.schedule-scene__title {
  font-size: 1.35rem;
  font-weight: 700;
  color: var(--color-text-primary);
}

.schedule-scene__subtitle {
  margin-top: 0.25rem;
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
}

.schedule-error {
  padding: 0.5rem 0.75rem;
  border-radius: 0.5rem;
  font-size: 0.8125rem;
  color: var(--color-danger);
  background: color-mix(in srgb, var(--color-danger) 10%, var(--color-surface-raised));
  border: 1px solid color-mix(in srgb, var(--color-danger) 25%, transparent);
}

.schedule-card {
  padding: 1rem 1.125rem;
  border-radius: var(--radius-outer);
  border: 1px solid var(--color-line);
  background: var(--color-bg-elevated);
}

.schedule-card__title {
  font-size: 0.9375rem;
  font-weight: 600;
  color: var(--color-text-primary);
  margin-bottom: 0.75rem;
}

.schedule-form {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.schedule-field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.schedule-field--checkbox {
  flex-direction: row;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
}

.schedule-field__label {
  font-size: 0.75rem;
  color: var(--color-text-secondary);
}

.schedule-field__input {
  padding: 0.375rem 0.5rem;
  border-radius: 0.375rem;
  border: 1px solid var(--color-border);
  background: var(--color-bg);
  color: var(--color-text-primary);
  font-size: 0.8125rem;
}

.schedule-field__hint {
  font-size: 0.6875rem;
  color: var(--color-text-secondary);
}

.schedule-empty {
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.schedule-empty__hint {
  font-size: 0.75rem;
  opacity: 0.8;
}

.schedule-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  list-style: none;
}

.schedule-item {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 0.75rem 0.875rem;
  border-radius: var(--radius-outer);
  border: 1px solid var(--color-line);
  background: var(--color-bg);
}

.schedule-item__head {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.schedule-item__kind {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--color-text-primary);
}

.schedule-item__cron {
  font-size: 0.75rem;
  padding: 0.125rem 0.375rem;
  border-radius: 0.25rem;
  background: var(--color-bg-elevated-2);
  color: var(--color-text-secondary);
}

.schedule-item__mode {
  font-size: 0.6875rem;
  padding: 0.125rem 0.375rem;
  border-radius: 999px;
  color: var(--color-text-secondary);
  background: var(--color-bg-elevated-2);
  border: 1px solid var(--color-line);
}

.schedule-item__badge {
  margin-left: auto;
  font-size: 0.6875rem;
  padding: 0.125rem 0.375rem;
  border-radius: 999px;
  color: var(--color-accent);
  background: color-mix(in srgb, var(--color-accent) 12%, transparent);
}

.schedule-item__badge.is-off {
  color: var(--color-text-secondary);
  background: var(--color-bg-elevated-2);
}

.schedule-item__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  font-size: 0.75rem;
  color: var(--color-text-secondary);
}

.schedule-item__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
}

.schedule-btn {
  padding: 0.25rem 0.625rem;
  border-radius: 0.375rem;
  border: 1px solid var(--color-border);
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 0.75rem;
  cursor: pointer;
  transition: color var(--dur-fast) var(--ease-out-quart);
}

.schedule-btn:hover:not(:disabled) {
  color: var(--color-text-primary);
  background: var(--color-bg-elevated-2);
}

.schedule-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.schedule-btn--danger:hover:not(:disabled) {
  color: var(--color-danger);
  border-color: color-mix(in srgb, var(--color-danger) 40%, transparent);
}

.schedule-btn--ghost {
  border-color: transparent;
  padding-left: 0;
}

.schedule-edit {
  display: flex;
  gap: 0.375rem;
}

.schedule-runs {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.schedule-runs__list {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  list-style: none;
}

.schedule-runs__item {
  display: flex;
  gap: 0.5rem;
  font-size: 0.75rem;
  color: var(--color-text-secondary);
}

.schedule-runs__status {
  color: var(--color-text-primary);
}

.schedule-runs__empty {
  font-size: 0.75rem;
  color: var(--color-text-secondary);
}

.schedule-confirm {
  position: fixed;
  inset: 0;
  z-index: 200;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1rem;
  background: rgba(0, 0, 0, 0.35);
}

.schedule-confirm__card {
  width: min(24rem, 100%);
  padding: 1rem 1.25rem;
  border-radius: var(--radius-outer);
  border: 1px solid var(--color-border);
  background: var(--color-bg-elevated);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.15);
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.schedule-confirm__title {
  font-size: 0.9375rem;
  font-weight: 600;
  color: var(--color-text-primary);
}

.schedule-confirm__desc {
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
}

.schedule-confirm__actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  margin-top: 0.25rem;
}
</style>