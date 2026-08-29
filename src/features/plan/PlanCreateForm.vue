<script setup lang="ts">
import { reactive, ref } from 'vue'
import { PhPlus, PhX } from '@phosphor-icons/vue'

import GameButton from '@/shared/components/GameButton.vue'
import GlassPanel from '@/shared/components/GlassPanel.vue'
import { planCopy } from '@/shared/copy/plan'
import { usePlanStore } from '@/stores/plan'

defineOptions({ name: 'PlanCreateForm' })

const emit = defineEmits<{ close: [] }>()

const planStore = usePlanStore()

const form = reactive({
  title: '',
  motivation: '',
  tasks: [] as Array<{ title: string; due_date: string }>,
})
const submitting = ref(false)
const titleError = ref(false)

function addTask() {
  form.tasks.push({ title: '', due_date: '' })
}

function removeTask(index: number) {
  form.tasks.splice(index, 1)
}

function cancel() {
  emit('close')
}

async function submit() {
  const title = form.title.trim()
  if (!title) {
    titleError.value = true
    return
  }
  titleError.value = false
  submitting.value = true
  const tasks = form.tasks
    .map((t) => ({ title: t.title.trim(), due_date: t.due_date || undefined }))
    .filter((t) => t.title)
  const ok = await planStore.createPlan({
    title,
    motivation: form.motivation.trim() || undefined,
    tasks: tasks.length > 0 ? tasks : undefined,
  })
  submitting.value = false
  if (ok) emit('close')
}
</script>

<template>
  <GlassPanel class="plan-create-form" padding>
    <div class="plan-create-form__head">
      <h3 class="plan-create-form__title">{{ planCopy.newPlan }}</h3>
      <button type="button" class="plan-create-form__close" @click="cancel">
        <PhX :size="16" />
      </button>
    </div>

    <label class="plan-create-form__field">
      <span class="plan-create-form__label">{{ planCopy.formTitleLabel }}</span>
      <input
        v-model="form.title"
        type="text"
        data-testid="plan-title-input"
        class="plan-create-form__input"
        :class="{ 'is-error': titleError }"
        :placeholder="planCopy.formTitlePlaceholder"
        maxlength="200"
        @input="titleError = false"
      />
    </label>

    <label class="plan-create-form__field">
      <span class="plan-create-form__label">{{ planCopy.formMotivationLabel }}</span>
      <input
        v-model="form.motivation"
        type="text"
        data-testid="plan-motivation-input"
        class="plan-create-form__input"
        :placeholder="planCopy.formMotivationPlaceholder"
      />
    </label>

    <div class="plan-create-form__field">
      <span class="plan-create-form__label">{{ planCopy.formTasksLabel }}</span>
      <div
        v-for="(task, index) in form.tasks"
        :key="index"
        class="plan-create-form__task-row"
      >
        <input
          v-model="task.title"
          type="text"
          data-testid="task-title-input"
          class="plan-create-form__input plan-create-form__task-title"
          :placeholder="planCopy.formTaskPlaceholder"
          maxlength="200"
        />
        <input
          v-model="task.due_date"
          type="date"
          class="plan-create-form__input plan-create-form__task-due"
          :aria-label="planCopy.formTaskDueLabel"
        />
        <button
          type="button"
          class="plan-create-form__remove"
          :title="planCopy.formRemoveTask"
          @click="removeTask(index)"
        >
          <PhX :size="14" />
        </button>
      </div>
      <button type="button" class="plan-create-form__add-task" data-testid="form-add-task" @click="addTask">
        <PhPlus :size="14" />
        {{ planCopy.formAddTask }}
      </button>
    </div>

    <div class="plan-create-form__actions">
      <GameButton variant="ghost" :disabled="submitting" @click="cancel">
        {{ planCopy.formCancel }}
      </GameButton>
      <GameButton variant="primary" :disabled="submitting" data-testid="plan-submit" @click="submit">
        {{ planCopy.formSubmit }}
      </GameButton>
    </div>
  </GlassPanel>
</template>

<style scoped>
.plan-create-form {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
.plan-create-form__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.plan-create-form__title {
  margin: 0;
  font-family: var(--font-ui);
  font-size: 1rem;
  font-weight: 700;
  color: var(--color-text-primary);
}
.plan-create-form__close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  padding: 0.25rem;
  border-radius: 0.375rem;
}
.plan-create-form__close:hover {
  color: var(--color-text-primary);
  background: var(--color-bg-elevated-2);
}
.plan-create-form__field {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}
.plan-create-form__label {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--color-text-secondary);
}
.plan-create-form__input {
  border: 1px solid var(--color-border);
  border-radius: 0.5rem;
  background: var(--color-bg);
  color: var(--color-text-primary);
  font-size: 0.875rem;
  padding: 0.5rem 0.75rem;
  outline: none;
  transition: border-color var(--motion-duration) var(--motion-ease);
}
.plan-create-form__input:focus {
  border-color: var(--color-accent);
}
.plan-create-form__input.is-error {
  border-color: var(--color-danger, #b3563e);
}
.plan-create-form__task-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.plan-create-form__task-title {
  flex: 1;
}
.plan-create-form__task-due {
  width: 8.5rem;
}
.plan-create-form__remove {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  padding: 0.375rem;
  border-radius: 0.375rem;
}
.plan-create-form__remove:hover {
  color: var(--color-danger, #b3563e);
  background: color-mix(in srgb, var(--color-danger, #b3563e) 8%, transparent);
}
.plan-create-form__add-task {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  align-self: flex-start;
  border: 1px dashed var(--color-border);
  border-radius: 0.5rem;
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 0.8125rem;
  padding: 0.375rem 0.75rem;
  cursor: pointer;
}
.plan-create-form__add-task:hover {
  color: var(--color-accent);
  border-color: var(--color-accent);
}
.plan-create-form__actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
}
</style>
