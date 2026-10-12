<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import GameButton from '@/shared/components/GameButton.vue'
import { customSkillsCopy as copy } from '@/shared/copy/customSkills'
import type { CustomSkill, CustomSkillInput } from '@/shared/api/customSkills'
import { useCustomSkillsStore } from '@/stores/customSkills'

defineOptions({ name: 'CustomSkillsManager' })

const store = useCustomSkillsStore()

const draft = reactive({
  name: '',
  description: '',
  triggers: '',
  instruction: '',
  enabled: true,
})

const editingId = ref<number | null>(null)
const showDeleteConfirm = ref(false)
const pendingDeleteId = ref<number | null>(null)

const editing = computed(() => editingId.value !== null)

function parseTriggers(raw: string): string[] {
  return raw
    .split(/[,，]/)
    .map((t) => t.trim())
    .filter((t) => t.length > 0)
}

const canSubmit = computed(
  () => draft.name.trim().length > 0 && draft.instruction.trim().length > 0 && parseTriggers(draft.triggers).length > 0,
)

function resetDraft(): void {
  draft.name = ''
  draft.description = ''
  draft.triggers = ''
  draft.instruction = ''
  draft.enabled = true
  editingId.value = null
}

async function onSubmit(): Promise<void> {
  if (!canSubmit.value) return
  const body: CustomSkillInput = {
    name: draft.name.trim(),
    description: draft.description.trim(),
    triggers: parseTriggers(draft.triggers),
    instruction: draft.instruction.trim(),
    enabled: draft.enabled,
  }
  try {
    if (editing.value && editingId.value !== null) {
      await store.update(editingId.value, body)
    } else {
      await store.create(body)
    }
    resetDraft()
  } catch {
    // surfaced via store.error
  }
}

function startEdit(skill: CustomSkill): void {
  editingId.value = skill.id
  draft.name = skill.name
  draft.description = skill.description
  draft.triggers = skill.triggers.join(', ')
  draft.instruction = skill.instruction
  draft.enabled = skill.enabled
}

async function onToggle(skill: CustomSkill): Promise<void> {
  try {
    await store.toggle(skill.id, !skill.enabled)
  } catch {
    // surfaced via store.error
  }
}

function askDelete(id: number): void {
  pendingDeleteId.value = id
  showDeleteConfirm.value = true
}

async function onDeleteConfirm(): Promise<void> {
  const id = pendingDeleteId.value
  showDeleteConfirm.value = false
  pendingDeleteId.value = null
  if (id === null) return
  try {
    await store.remove(id)
    if (editingId.value === id) resetDraft()
  } catch {
    // surfaced via store.error
  }
}

onMounted(() => {
  void store.loadAll().catch(() => undefined)
})
</script>

<template>
  <div class="custom-skills">
    <p class="custom-skills__intro">{{ copy.intro }}</p>
    <p class="custom-skills__review">{{ copy.reviewHint }}</p>

    <form class="custom-skills__form" @submit.prevent="onSubmit">
      <label class="settings-field">
        <span class="settings-field__label">{{ copy.nameLabel }}</span>
        <input
          v-model="draft.name"
          data-testid="custom-skill-name"
          class="settings-field__input ink-underline"
          maxlength="40"
          :placeholder="copy.namePlaceholder"
        />
      </label>

      <label class="settings-field">
        <span class="settings-field__label">{{ copy.descriptionLabel }}</span>
        <input
          v-model="draft.description"
          data-testid="custom-skill-description"
          class="settings-field__input ink-underline"
          maxlength="120"
          :placeholder="copy.descriptionPlaceholder"
        />
      </label>

      <label class="settings-field">
        <span class="settings-field__label">{{ copy.triggersLabel }}</span>
        <input
          v-model="draft.triggers"
          data-testid="custom-skill-triggers"
          class="settings-field__input ink-underline"
          :placeholder="copy.triggersPlaceholder"
        />
        <span class="settings-field__hint">{{ copy.triggersHint }}</span>
      </label>

      <label class="settings-field">
        <span class="settings-field__label">{{ copy.instructionLabel }}</span>
        <textarea
          v-model="draft.instruction"
          data-testid="custom-skill-instruction"
          class="settings-field__input settings-field__textarea ink-underline"
          maxlength="500"
          rows="3"
          :placeholder="copy.instructionPlaceholder"
        />
      </label>

      <label class="settings-field settings-field--checkbox">
        <input v-model="draft.enabled" data-testid="custom-skill-enabled" type="checkbox" />
        <span>{{ copy.enabledLabel }}</span>
      </label>

      <div class="custom-skills__form-actions">
        <GameButton type="submit" :disabled="!canSubmit || store.saving" data-testid="custom-skill-submit">
          {{ editing ? copy.save : copy.create }}
        </GameButton>
        <GameButton
          v-if="editing"
          variant="ghost"
          data-testid="custom-skill-cancel"
          @click="resetDraft"
        >
          {{ copy.cancel }}
        </GameButton>
      </div>
    </form>

    <p v-if="store.error" class="custom-skills__error">{{ store.error }}</p>

    <p v-if="store.skills.length === 0" class="custom-skills__empty">
      {{ copy.empty }}<br />
      <span class="custom-skills__empty-hint">{{ copy.emptyHint }}</span>
    </p>

    <ul v-else class="custom-skills__list">
      <li
        v-for="skill in store.skills"
        :key="skill.id"
        data-testid="custom-skill-item"
        class="custom-skills__item"
      >
        <div class="custom-skills__item-head">
          <span class="custom-skills__item-name">{{ skill.name }}</span>
          <span
            class="custom-skills__item-state"
            :class="{ 'custom-skills__item-state--off': !skill.enabled }"
          >
            {{ skill.enabled ? copy.enable : copy.disable }}
          </span>
        </div>
        <p v-if="skill.description" class="custom-skills__item-desc">{{ skill.description }}</p>
        <p class="custom-skills__item-instruction">{{ skill.instruction }}</p>
        <div class="custom-skills__item-triggers">
          <span
            v-for="trigger in skill.triggers"
            :key="trigger"
            data-testid="custom-skill-trigger"
            class="custom-skills__trigger"
          >
            {{ trigger }}
          </span>
        </div>
        <div class="custom-skills__item-actions">
          <button
            type="button"
            data-testid="custom-skill-toggle"
            class="custom-skills__action"
            @click="onToggle(skill)"
          >
            {{ skill.enabled ? copy.disable : copy.enable }}
          </button>
          <button
            type="button"
            data-testid="custom-skill-edit"
            class="custom-skills__action"
            @click="startEdit(skill)"
          >
            {{ copy.edit }}
          </button>
          <button
            type="button"
            data-testid="custom-skill-delete"
            class="custom-skills__action"
            @click="askDelete(skill.id)"
          >
            {{ copy.delete }}
          </button>
        </div>
      </li>
    </ul>

    <div v-if="showDeleteConfirm" class="custom-skills__confirm">
      <p class="custom-skills__confirm-title">{{ copy.confirmDeleteTitle }}</p>
      <p class="custom-skills__confirm-desc">{{ copy.confirmDeleteDesc }}</p>
      <div class="custom-skills__form-actions">
        <GameButton data-testid="custom-skill-delete-confirm" @click="onDeleteConfirm">
          {{ copy.confirmDelete }}
        </GameButton>
        <GameButton variant="ghost" @click="showDeleteConfirm = false">{{ copy.cancel }}</GameButton>
      </div>
    </div>
  </div>
</template>

<style scoped>
.custom-skills {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.custom-skills__intro {
  font-size: 0.8125rem;
  line-height: 1.7;
  color: var(--color-text-secondary);
}

.custom-skills__review {
  font-size: 0.75rem;
  line-height: 1.6;
  color: var(--color-text-faint);
}

.custom-skills__form {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  padding: 0.75rem 0.125rem;
  border-top: 1px solid var(--color-line);
}

.settings-field {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  margin-bottom: 0.625rem;
}

.settings-field--checkbox {
  flex-direction: row;
  align-items: center;
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
}

.settings-field--checkbox input {
  accent-color: var(--color-accent);
}

.settings-field__label {
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
}

.settings-field__input {
  padding: 0.375rem 0.125rem;
  border-radius: 0;
  color: var(--color-text-primary);
  font-size: 0.875rem;
}

.settings-field__textarea {
  resize: vertical;
  font-family: inherit;
  line-height: 1.6;
}

.settings-field__input::placeholder {
  color: var(--color-text-faint);
}

.settings-field__hint {
  font-size: 0.75rem;
  color: var(--color-text-secondary);
  margin-top: 0.125rem;
}

.custom-skills__form-actions {
  display: flex;
  gap: 0.5rem;
  margin-top: 0.25rem;
}

.custom-skills__error {
  font-size: 0.8125rem;
  color: var(--color-danger, #c0392b);
}

.custom-skills__empty {
  font-size: 0.8125rem;
  line-height: 1.7;
  color: var(--color-text-secondary);
  padding: 0.5rem 0.125rem;
}

.custom-skills__empty-hint {
  color: var(--color-text-faint);
}

.custom-skills__list {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 0;
  margin: 0;
}

.custom-skills__item {
  padding: 0.75rem 0.125rem;
  border-top: 1px solid var(--color-line);
}

.custom-skills__item-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.5rem;
}

.custom-skills__item-name {
  font-size: 0.9375rem;
  font-weight: 600;
  color: var(--color-text-primary);
}

.custom-skills__item-state {
  font-size: 0.75rem;
  color: var(--color-accent);
}

.custom-skills__item-state--off {
  color: var(--color-text-faint);
}

.custom-skills__item-desc {
  margin-top: 0.25rem;
  font-size: 0.75rem;
  color: var(--color-text-secondary);
}

.custom-skills__item-instruction {
  margin-top: 0.375rem;
  font-size: 0.8125rem;
  line-height: 1.6;
  color: var(--color-text-primary);
}

.custom-skills__item-triggers {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
  margin-top: 0.5rem;
}

.custom-skills__trigger {
  padding: 0.125rem 0.5rem;
  border: 1px solid var(--color-line);
  border-radius: var(--radius-seal);
  font-size: 0.75rem;
  color: var(--color-text-secondary);
}

.custom-skills__item-actions {
  display: flex;
  gap: 0.75rem;
  margin-top: 0.625rem;
}

.custom-skills__action {
  background: none;
  border: none;
  padding: 0;
  font-size: 0.75rem;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: color var(--dur-fast) var(--ease-out-quart);
}

.custom-skills__action:hover {
  color: var(--color-accent);
}

.custom-skills__confirm {
  padding: 0.75rem 0.125rem;
  border-top: 1px solid var(--color-line);
}

.custom-skills__confirm-title {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--color-text-primary);
}

.custom-skills__confirm-desc {
  margin-top: 0.25rem;
  font-size: 0.75rem;
  color: var(--color-text-secondary);
}
</style>