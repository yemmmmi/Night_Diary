<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import GameButton from '@/shared/components/GameButton.vue'
import {
  createModel,
  deleteModel,
  getModelsStatus,
  listModels,
  testModelConnection,
  testStoredModelConnection,
  updateModel,
  type ModelProvider,
  type ModelStatusResponse,
  type ModelTier,
} from '@/shared/api/models'
import { MODEL_PRESETS, modelsCopy, type ModelPreset } from '@/shared/copy/models'
import { formatApiError } from '@/shared/utils/apiError'
import { openExternal } from '@/shared/utils/openExternal'

const tierLabels: Record<ModelTier, string> = {
  light: '轻量模型',
  medium: '标准模型',
  heavy: '深度分析模型',
  default: '默认使用',
}

const models = ref<ModelProvider[]>([])
const modelStatus = ref<ModelStatusResponse | null>(null)
const loading = ref(true)
const saving = ref(false)
const testing = ref(false)
const testingModelId = ref<number | null>(null)
const error = ref<string | null>(null)
const success = ref<string | null>(null)
const testResult = ref<string | null>(null)
const editingModel = ref<ModelProvider | null>(null)
const selectedPreset = ref<ModelPreset | null>(null)

const form = reactive({
  model_name: '',
  api_key: '',
  base_url: 'https://api.deepseek.com',
  tier: 'default' as ModelTier,
  is_active: true,
})

const editForm = reactive({
  model_name: '',
  api_key: '',
  base_url: '',
  tier: 'default' as ModelTier,
  is_active: false,
})

function applyPreset(preset: ModelPreset) {
  selectedPreset.value = preset
  form.base_url = preset.baseUrl
  if (preset.defaultModel) form.model_name = preset.defaultModel
  form.tier = preset.suggestedTier
  error.value = null
  success.value = null
  testResult.value = null
}

function openKeyUrl(url: string) {
  if (url) void openExternal(url)
}

async function refresh() {
  loading.value = true
  error.value = null
  try {
    const [list, status] = await Promise.all([listModels(), getModelsStatus()])
    models.value = list
    modelStatus.value = status
  } catch (err) {
    error.value = formatApiError(err, '加载模型列表失败')
  } finally {
    loading.value = false
  }
}

const activeTierSummary = computed(() => {
  if (!modelStatus.value) return null
  const configured = modelStatus.value.tiers.filter((t) => t.configured)
  if (configured.length === 0) {
    if (modelStatus.value.env_fallback) {
      return `当前使用环境变量模型：${modelStatus.value.env_model_name ?? '未命名'}`
    }
    return '尚未配置任何 AI 模型，AI 回信将使用降级模板'
  }
  return configured
    .map((t) => `${tierLabels[t.tier] ?? t.tier} → ${t.model_name}`)
    .join('；')
})

async function submit() {
  saving.value = true
  error.value = null
  success.value = null
  testResult.value = null
  try {
    await createModel({ ...form })
    success.value = '模型已保存'
    form.model_name = ''
    form.api_key = ''
    await refresh()
  } catch (err) {
    error.value = formatApiError(err, '保存失败')
  } finally {
    saving.value = false
  }
}

async function runConnectionTest() {
  if (!form.api_key.trim() || !form.base_url.trim()) {
    testResult.value = '请先填写 API 地址和密钥'
    return
  }
  testing.value = true
  testResult.value = null
  error.value = null
  try {
    const result = await testModelConnection({
      model_name: form.model_name.trim() || 'deepseek-chat',
      api_key: form.api_key,
      base_url: form.base_url,
    })
    testResult.value = result.ok
      ? result.message ?? '连接成功，可以保存'
      : result.message ?? '连接失败'
  } catch (err) {
    testResult.value = formatApiError(err, '连接测试失败')
  } finally {
    testing.value = false
  }
}

async function runStoredModelTest(model: ModelProvider) {
  if (!model.has_api_key) {
    testResult.value = '该模型未配置 API Key'
    return
  }
  testingModelId.value = model.id
  testResult.value = null
  error.value = null
  try {
    const result = await testStoredModelConnection(model.id)
    testResult.value = `${model.model_name}：${result.ok ? result.message ?? '连接成功' : result.message ?? '连接失败'}`
  } catch (err) {
    testResult.value = formatApiError(err, '连接测试失败')
  } finally {
    testingModelId.value = null
  }
}

async function runEditConnectionTest() {
  if (!editingModel.value) return
  testing.value = true
  testResult.value = null
  error.value = null
  try {
    const result = editForm.api_key.trim()
      ? await testModelConnection({
          model_name: editForm.model_name.trim() || 'deepseek-chat',
          api_key: editForm.api_key.trim(),
          base_url: editForm.base_url.trim(),
        })
      : await testStoredModelConnection(editingModel.value.id)
    testResult.value = result.ok
      ? result.message ?? '连接成功'
      : result.message ?? '连接失败'
  } catch (err) {
    testResult.value = formatApiError(err, '连接测试失败')
  } finally {
    testing.value = false
  }
}

async function toggleActive(model: ModelProvider) {
  error.value = null
  try {
    await updateModel(model.id, { is_active: !model.is_active })
    await refresh()
  } catch (err) {
    error.value = formatApiError(err, '更新失败')
  }
}

async function remove(model: ModelProvider) {
  if (!window.confirm(`确定要移除模型「${model.model_name}」吗？`)) return
  error.value = null
  try {
    await deleteModel(model.id)
    if (editingModel.value?.id === model.id) cancelEdit()
    await refresh()
  } catch (err) {
    error.value = formatApiError(err, '删除失败')
  }
}

function startEdit(model: ModelProvider) {
  editingModel.value = model
  editForm.model_name = model.model_name
  editForm.api_key = ''
  editForm.base_url = model.base_url ?? 'https://api.deepseek.com/v1'
  editForm.tier = model.tier
  editForm.is_active = model.is_active
  error.value = null
  success.value = null
}

function cancelEdit() {
  editingModel.value = null
}

async function saveEdit() {
  if (!editingModel.value) return
  saving.value = true
  error.value = null
  success.value = null
  try {
    await updateModel(editingModel.value.id, {
      model_name: editForm.model_name.trim(),
      base_url: editForm.base_url.trim(),
      tier: editForm.tier,
      is_active: editForm.is_active,
      ...(editForm.api_key.trim() ? { api_key: editForm.api_key.trim() } : {}),
    })
    success.value = '模型已更新'
    cancelEdit()
    await refresh()
  } catch (err) {
    error.value = formatApiError(err, '更新失败')
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  void refresh()
})
</script>

<template>
  <div class="llm-config">
    <p v-if="activeTierSummary" class="llm-config__status">{{ activeTierSummary }}</p>

    <form class="settings-form" @submit.prevent="submit">
      <div class="llm-config__presets">
        <p class="llm-config__presets-title">{{ modelsCopy.presetSectionTitle }}</p>
        <p class="llm-config__presets-hint">{{ modelsCopy.presetSectionHint }}</p>
        <div class="preset-grid">
          <div
            v-for="preset in MODEL_PRESETS"
            :key="preset.key"
            class="preset-card"
            :class="{ 'preset-card--active': selectedPreset?.key === preset.key }"
            role="button"
            tabindex="0"
            @click="applyPreset(preset)"
            @keydown.enter="applyPreset(preset)"
            @keydown.space.prevent="applyPreset(preset)"
          >
            <span class="preset-card__name">{{ preset.name }}</span>
            <span v-if="preset.freeHint" class="preset-card__free">{{ preset.freeHint }}</span>
            <span class="preset-card__desc">{{ preset.description }}</span>
            <button
              v-if="preset.keyUrl"
              type="button"
              class="preset-card__link"
              @click.stop="openKeyUrl(preset.keyUrl)"
            >
              {{ modelsCopy.getKey }}
            </button>
          </div>
        </div>
      </div>

      <label class="settings-form__field">
        <span class="settings-form__label">模型名称</span>
        <select
          v-if="selectedPreset && selectedPreset.models.length > 0"
          v-model="form.model_name"
          class="settings-form__input"
        >
          <option v-for="opt in selectedPreset.models" :key="opt.value" :value="opt.value">
            {{ opt.label }}
          </option>
        </select>
        <input
          v-else
          v-model="form.model_name"
          required
          class="settings-form__input"
          :placeholder="modelsCopy.modelInputPlaceholder"
        />
      </label>
      <label class="settings-form__field">
        <span class="settings-form__label">模型层级</span>
        <select v-model="form.tier" class="settings-form__input">
          <option v-for="(label, tier) in tierLabels" :key="tier" :value="tier">{{ label }}</option>
        </select>
      </label>
      <label class="settings-form__field">
        <span class="settings-form__label">API 地址</span>
        <input v-model="form.base_url" required class="settings-form__input" placeholder="https://api.deepseek.com/v1" />
      </label>
      <label class="settings-form__field">
        <span class="settings-form__label">API 密钥</span>
        <input v-model="form.api_key" required type="password" class="settings-form__input" placeholder="sk-..." />
      </label>
      <label class="settings-form__checkbox">
        <input v-model="form.is_active" type="checkbox" />
        <span>设为该层级的当前使用模型</span>
      </label>
      <div class="settings-form__actions">
        <GameButton type="button" variant="secondary" :disabled="testing" @click="runConnectionTest">
          {{ testing ? '测试中…' : '测试连接' }}
        </GameButton>
        <GameButton type="submit" variant="primary" :disabled="saving">{{ saving ? '保存中…' : '保存' }}</GameButton>
      </div>
      <p v-if="testResult" class="settings-form__msg">{{ testResult }}</p>
      <p v-if="success" class="settings-form__msg settings-form__msg--ok">{{ success }}</p>
      <p v-if="error" class="settings-form__msg settings-form__msg--err">{{ error }}</p>
    </form>

    <div class="llm-config__list">
      <h3 class="llm-config__list-title">已配置模型</h3>
      <p v-if="loading" class="llm-config__hint">加载中…</p>
      <p v-else-if="models.length === 0" class="llm-config__hint">暂无模型，请先添加。</p>
      <ul v-else class="models-list">
        <li v-for="model in models" :key="model.id" class="models-list__item">
          <div class="models-list__info">
            <p class="models-list__name">{{ model.model_name }}</p>
            <p class="models-list__meta">
              <span class="models-list__tier">{{ tierLabels[model.tier] || model.tier }}</span>
              <span class="models-list__sep">·</span>
              <span>{{ model.has_api_key ? '密钥已设置' : '密钥未设置' }}</span>
            </p>
          </div>
          <div class="models-list__actions">
            <GameButton
              variant="ghost"
              :disabled="testingModelId === model.id || !model.has_api_key"
              @click="runStoredModelTest(model)"
            >
              {{ testingModelId === model.id ? '测试中…' : '测试连接' }}
            </GameButton>
            <GameButton :variant="model.is_active ? 'secondary' : 'ghost'" @click="toggleActive(model)">
              {{ model.is_active ? '当前使用' : '切换至此' }}
            </GameButton>
            <GameButton variant="ghost" @click="startEdit(model)">编辑</GameButton>
            <GameButton variant="ghost" @click="remove(model)">移除</GameButton>
          </div>
        </li>
      </ul>
    </div>

    <form v-if="editingModel" class="settings-form llm-config__edit" @submit.prevent="saveEdit">
      <h3 class="llm-config__list-title">编辑模型</h3>
      <label class="settings-form__field">
        <span class="settings-form__label">模型名称</span>
        <input v-model="editForm.model_name" required class="settings-form__input" />
      </label>
      <label class="settings-form__field">
        <span class="settings-form__label">模型层级</span>
        <select v-model="editForm.tier" class="settings-form__input">
          <option v-for="(label, tier) in tierLabels" :key="tier" :value="tier">{{ label }}</option>
        </select>
      </label>
      <label class="settings-form__field">
        <span class="settings-form__label">API 地址</span>
        <input v-model="editForm.base_url" required class="settings-form__input" />
      </label>
      <label class="settings-form__field">
        <span class="settings-form__label">新 API 密钥（留空则不修改）</span>
        <input v-model="editForm.api_key" type="password" class="settings-form__input" placeholder="sk-..." />
      </label>
      <label class="settings-form__checkbox">
        <input v-model="editForm.is_active" type="checkbox" />
        <span>设为该层级的当前使用模型</span>
      </label>
      <div class="settings-form__actions">
        <GameButton type="button" variant="secondary" :disabled="testing" @click="runEditConnectionTest">
          {{ testing ? '测试中…' : '测试连接' }}
        </GameButton>
        <GameButton type="button" variant="ghost" @click="cancelEdit">取消</GameButton>
        <GameButton type="submit" variant="primary" :disabled="saving">{{ saving ? '保存中…' : '保存更改' }}</GameButton>
      </div>
      <p v-if="testResult && editingModel" class="settings-form__msg">{{ testResult }}</p>
    </form>
  </div>
</template>

<style scoped>
.llm-config {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.llm-config__status,
.llm-config__hint {
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
  line-height: 1.6;
}

.llm-config__list-title {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--color-text-primary);
  margin-bottom: 0.625rem;
}

.llm-config__edit {
  padding-top: 0.75rem;
  border-top: 1px solid var(--color-border);
}

.settings-form {
  display: grid;
  gap: 0.875rem;
}

.settings-form__field {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.settings-form__label {
  font-size: 0.8125rem;
  font-weight: 500;
  color: var(--color-text-secondary);
}

.settings-form__input {
  width: 100%;
  padding: 0.625rem 0.75rem;
  border-radius: 0.625rem;
  border: 1px solid var(--color-border);
  background: var(--color-bg-elevated-2);
  color: var(--color-text-primary);
  font-size: 0.875rem;
}

.settings-form__checkbox {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
}

.settings-form__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.625rem;
}

.settings-form__msg {
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
}

.settings-form__msg--ok {
  color: var(--color-success);
}

.settings-form__msg--err {
  color: var(--color-danger);
}

.models-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.models-list__item {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.625rem;
  padding: 0.75rem 0;
  border-bottom: 1px solid var(--color-border);
}

.models-list__item:last-child {
  border-bottom: none;
}

.models-list__name {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--color-text-primary);
}

.models-list__meta {
  margin-top: 0.1875rem;
  font-size: 0.75rem;
  color: var(--color-text-secondary);
}

.models-list__tier {
  color: var(--color-accent);
}

.models-list__sep {
  margin: 0 0.375rem;
  opacity: 0.4;
}

.models-list__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
}

.llm-config__presets {
  padding-bottom: 0.875rem;
  border-bottom: 1px solid var(--color-border);
  margin-bottom: 0.25rem;
}

.llm-config__presets-title {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--color-text-primary);
  margin-bottom: 0.25rem;
}

.llm-config__presets-hint {
  font-size: 0.75rem;
  color: var(--color-text-secondary);
  margin-bottom: 0.625rem;
}

.preset-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(11rem, 1fr));
  gap: 0.5rem;
}

.preset-card {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  min-height: 7.5rem;
  padding: 0.625rem 0.75rem;
  border-radius: 0.625rem;
  border: 1px solid var(--color-border);
  background: var(--color-bg-elevated-2);
  text-align: left;
  cursor: pointer;
  transition:
    border-color 0.2s ease,
    background 0.2s ease;
}

.preset-card:hover {
  border-color: var(--color-accent);
  background: color-mix(in srgb, var(--color-accent) 8%, var(--color-bg-elevated-2));
}

.preset-card--active {
  border-color: var(--color-accent);
  background: color-mix(in srgb, var(--color-accent) 12%, var(--color-bg-elevated-2));
}

.preset-card__name {
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--color-text-primary);
}

.preset-card__free {
  font-size: 0.6875rem;
  color: var(--color-success);
}

.preset-card__desc {
  font-size: 0.6875rem;
  line-height: 1.4;
  color: var(--color-text-secondary);
}

.preset-card__link {
  margin-top: auto;
  padding: 0;
  border: none;
  background: none;
  font-size: 0.6875rem;
  color: var(--color-accent);
  cursor: pointer;
  text-align: left;
  text-decoration: none;
  align-self: flex-start;
}

.preset-card__link:hover {
  text-decoration: underline;
}
</style>
