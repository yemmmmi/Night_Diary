<script setup lang="ts">
import { ref } from 'vue'
import { useSettingsStore, PRESET_REPLIERS, type UserReplier } from '@/stores/settings'

const settings = useSettingsStore()
settings.load()

const showForm = ref(false)
const editingId = ref<string | null>(null)
const formName = ref('')
const formPersona = ref('')
const formError = ref<string | null>(null)

function openNew() {
  editingId.value = null
  formName.value = ''
  formPersona.value = ''
  formError.value = null
  showForm.value = true
}

function openEdit(replier: UserReplier) {
  editingId.value = replier.id
  formName.value = replier.name
  formPersona.value = replier.persona
  formError.value = null
  showForm.value = true
}

function closeForm() {
  showForm.value = false
  editingId.value = null
}

function saveForm() {
  const name = formName.value.trim()
  const persona = formPersona.value.trim()
  if (!name) {
    formError.value = '昵称不能为空'
    return
  }
  if (!persona) {
    formError.value = '人设描述不能为空'
    return
  }
  if (editingId.value) {
    settings.updateUserReplier(editingId.value, name, persona)
  } else {
    settings.addUserReplier(name, persona)
  }
  closeForm()
}

function deleteReplier(id: string) {
  settings.deleteUserReplier(id)
}
</script>

<template>
  <div class="replier-manager">
    <!-- Preset repliers -->
    <div class="replier-manager__group">
      <button
        v-for="preset in PRESET_REPLIERS"
        :key="preset.id"
        type="button"
        class="replier-option"
        :class="{ 'is-active': settings.activeReplierId === preset.id }"
        @click="settings.setActiveReplier(preset.id)"
      >
        <span class="replier-option__name">{{ preset.name }}</span>
        <span class="replier-option__desc">{{ preset.persona }}</span>
      </button>
    </div>

    <!-- User-defined repliers -->
    <div class="replier-manager__user-section">
      <div
        v-for="replier in settings.userRepliers"
        :key="replier.id"
        class="replier-option replier-option--user"
        :class="{ 'is-active': settings.activeReplierId === replier.id }"
      >
        <button
          type="button"
          class="replier-option__body"
          @click="settings.setActiveReplier(replier.id)"
        >
          <span class="replier-option__name">{{ replier.name }}</span>
          <span class="replier-option__desc">{{ replier.persona }}</span>
        </button>
        <div class="replier-option__actions">
          <button
            type="button"
            class="replier-option__action"
            title="编辑"
            @click="openEdit(replier)"
          >
            &#9998;
          </button>
          <button
            type="button"
            class="replier-option__action replier-option__action--danger"
            title="删除"
            @click="deleteReplier(replier.id)"
          >
            &times;
          </button>
        </div>
      </div>

      <button type="button" class="replier-manager__add" @click="openNew">
        + 新建自定义人设
      </button>
    </div>

    <!-- Edit / Create form overlay -->
    <Teleport to="body">
      <div v-if="showForm" class="replier-form-overlay" @click.self="closeForm">
        <div class="replier-form-card">
          <p class="replier-form__title">
            {{ editingId ? '编辑人设' : '新建自定义人设' }}
          </p>
          <label class="replier-form__field">
            <span>昵称</span>
            <input
              v-model="formName"
              class="replier-form__input"
              maxlength="24"
              placeholder="给回信者起个名字"
            />
          </label>
          <label class="replier-form__field">
            <span>人设描述</span>
            <textarea
              v-model="formPersona"
              class="replier-form__textarea"
              rows="3"
              placeholder="描述回信者的性格和风格，例如：一个退休的图书馆馆长，说话慢条斯理…"
            />
          </label>
          <p v-if="formError" class="replier-form__error">{{ formError }}</p>
          <div class="replier-form__actions">
            <button type="button" class="replier-form__btn replier-form__btn--cancel" @click="closeForm">
              取消
            </button>
            <button type="button" class="replier-form__btn replier-form__btn--save" @click="saveForm">
              保存
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.replier-manager {
  display: flex;
  flex-direction: column;
}

.replier-option {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  width: 100%;
  text-align: left;
  padding: 0.625rem 0.875rem;
  border: 1px solid var(--color-border);
  border-radius: 0.625rem;
  background: var(--color-bg-elevated);
  cursor: pointer;
  transition: border-color var(--motion-duration) var(--motion-ease);
}

.replier-option:hover {
  border-color: var(--color-accent-muted);
}

.replier-option.is-active {
  border-color: var(--color-accent);
  background: color-mix(in srgb, var(--color-accent) 6%, var(--color-bg-elevated));
}

.replier-option__body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
  text-align: left;
  border: none;
  background: none;
  padding: 0;
  cursor: pointer;
}

.replier-option--user {
  padding-right: 0.5rem;
}

.replier-option__name {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--color-text-primary);
}

.replier-option__desc {
  font-size: 0.75rem;
  color: var(--color-text-secondary);
  line-height: 1.4;
}

.replier-option__actions {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  flex-shrink: 0;
}

.replier-option__action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.5rem;
  height: 1.5rem;
  border: none;
  border-radius: 0.375rem;
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 0.75rem;
  cursor: pointer;
  transition: background var(--motion-duration) var(--motion-ease);
}

.replier-option__action:hover {
  background: var(--color-bg-elevated-2);
  color: var(--color-text-primary);
}

.replier-option__action--danger:hover {
  background: color-mix(in srgb, var(--color-danger) 12%, transparent);
  color: var(--color-danger);
}

.replier-manager__group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin-bottom: 1rem;
}

.replier-manager__user-section {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.replier-manager__add {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.5rem 0.75rem;
  border: 1px dashed var(--color-border);
  border-radius: 0.625rem;
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 0.8125rem;
  cursor: pointer;
  transition: border-color var(--motion-duration) var(--motion-ease);
}

.replier-manager__add:hover {
  border-color: var(--color-accent-muted);
  color: var(--color-text-primary);
}

/* Form overlay */
.replier-form-overlay {
  position: fixed;
  inset: 0;
  z-index: 200;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.35);
  backdrop-filter: blur(4px);
}

.replier-form-card {
  width: min(24rem, calc(100vw - 2rem));
  padding: 1.5rem;
  border-radius: var(--radius-outer);
  border: 1px solid var(--color-border);
  background: var(--color-bg-elevated);
}

.replier-form__title {
  font-size: 0.9375rem;
  font-weight: 600;
  color: var(--color-text-primary);
  margin-bottom: 1rem;
}

.replier-form__field {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  margin-bottom: 0.875rem;
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
}

.replier-form__input,
.replier-form__textarea {
  padding: 0.625rem 0.75rem;
  border-radius: 0.625rem;
  border: 1px solid var(--color-border);
  background: var(--color-bg-elevated-2);
  color: var(--color-text-primary);
  font-family: var(--font-ui);
  font-size: 0.8125rem;
}

.replier-form__textarea {
  font-family: var(--font-diary);
  resize: vertical;
}

.replier-form__error {
  font-size: 0.75rem;
  color: var(--color-danger);
  margin-bottom: 0.5rem;
}

.replier-form__actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  margin-top: 0.5rem;
}

.replier-form__btn {
  padding: 0.5rem 1rem;
  border-radius: 0.5rem;
  border: 1px solid var(--color-border);
  font-size: 0.8125rem;
  cursor: pointer;
}

.replier-form__btn--cancel {
  background: var(--color-bg-elevated);
  color: var(--color-text-secondary);
}

.replier-form__btn--save {
  background: var(--color-accent);
  border-color: var(--color-accent);
  color: #fff;
  font-weight: 600;
}
</style>
