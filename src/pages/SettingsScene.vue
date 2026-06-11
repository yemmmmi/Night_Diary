<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { PhArrowLeft } from '@phosphor-icons/vue'

import GameButton from '@/shared/components/GameButton.vue'
import GlassPanel from '@/shared/components/GlassPanel.vue'
import {
  createModel,
  deleteModel,
  listModels,
  updateModel,
  type ModelProvider,
  type ModelTier,
} from '@/shared/api/models'

const tierLabels: Record<ModelTier, string> = {
  light: '轻量模型',
  medium: '标准模型',
  heavy: '深度分析模型',
  default: '默认使用',
}

const models = ref<ModelProvider[]>([])
const loading = ref(true)
const saving = ref(false)
const error = ref<string | null>(null)
const success = ref<string | null>(null)

const form = reactive({
  model_name: '',
  api_key: '',
  base_url: 'https://api.deepseek.com/v1',
  tier: 'default' as ModelTier,
  is_active: true,
})

async function refresh() {
  loading.value = true
  error.value = null
  try {
    models.value = await listModels()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载模型列表失败'
  } finally {
    loading.value = false
  }
}

async function submit() {
  saving.value = true
  error.value = null
  success.value = null
  try {
    await createModel({ ...form })
    success.value = '模型已保存'
    form.model_name = ''
    form.api_key = ''
    await refresh()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '保存失败'
  } finally {
    saving.value = false
  }
}

async function toggleActive(model: ModelProvider) {
  error.value = null
  try {
    await updateModel(model.id, { is_active: !model.is_active })
    await refresh()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '更新失败'
  }
}

async function remove(model: ModelProvider) {
  if (!window.confirm(`确定要移除模型「${model.model_name}」吗？`)) return
  error.value = null
  try {
    await deleteModel(model.id)
    await refresh()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '删除失败'
  }
}

onMounted(() => {
  void refresh()
})
</script>

<template>
  <main class="settings-scene">
    <div class="settings-scene__container">
      <!-- 页头 -->
      <header class="settings-scene__header">
        <RouterLink to="/" class="settings-scene__back">
          <PhArrowLeft :size="16" />
          返回
        </RouterLink>
        <div class="settings-scene__title-area">
          <h1 class="settings-scene__title">AI 模型设置</h1>
          <p class="settings-scene__subtitle">为不同场景选择合适的模型；所有数据仅存储在本地</p>
        </div>
      </header>

      <!-- 隐私声明 -->
      <GlassPanel class="settings-scene__privacy" elevated>
        <div class="privacy-block">
          <p class="privacy-block__title">夜记完全运行在你的电脑上</p>
          <p class="privacy-block__text">日记内容、AI 模型调用、所有数据均不经过第三方服务器。无需注册、无需登录。</p>
        </div>
      </GlassPanel>

      <!-- 添加模型表单 -->
      <GlassPanel elevated>
        <h2 class="section-heading">添加模型</h2>
        <form class="settings-form" @submit.prevent="submit">
          <label class="settings-form__field">
            <span class="settings-form__label">模型名称</span>
            <input
              v-model="form.model_name"
              required
              class="settings-form__input"
              placeholder="如 deepseek-chat"
            />
          </label>

          <label class="settings-form__field">
            <span class="settings-form__label">模型层级</span>
            <select v-model="form.tier" class="settings-form__input">
              <option v-for="(label, tier) in tierLabels" :key="tier" :value="tier">
                {{ label }}
              </option>
            </select>
          </label>

          <label class="settings-form__field">
            <span class="settings-form__label">API 地址</span>
            <input
              v-model="form.base_url"
              required
              class="settings-form__input"
              placeholder="https://api.deepseek.com/v1"
            />
          </label>

          <label class="settings-form__field">
            <span class="settings-form__label">API 密钥</span>
            <input
              v-model="form.api_key"
              required
              type="password"
              class="settings-form__input"
              placeholder="sk-..."
            />
          </label>

          <label class="settings-form__checkbox">
            <input v-model="form.is_active" type="checkbox" />
            <span>设为该层级的当前使用模型</span>
          </label>

          <div class="settings-form__actions">
            <GameButton type="submit" variant="primary" :disabled="saving">
              {{ saving ? '保存中…' : '保存' }}
            </GameButton>
            <p v-if="success" class="settings-form__msg settings-form__msg--ok">{{ success }}</p>
            <p v-if="error" class="settings-form__msg settings-form__msg--err">{{ error }}</p>
          </div>
        </form>
      </GlassPanel>

      <!-- 已配置模型列表 -->
      <GlassPanel elevated>
        <h2 class="section-heading">已配置模型</h2>
        <p v-if="loading" class="settings-scene__hint">加载中…</p>
        <p v-else-if="models.length === 0" class="settings-scene__hint">暂无模型，请先添加。</p>
        <ul v-else class="models-list">
          <li
            v-for="model in models"
            :key="model.id"
            class="models-list__item"
          >
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
                :variant="model.is_active ? 'secondary' : 'ghost'"
                @click="toggleActive(model)"
              >
                {{ model.is_active ? '当前使用' : '切换至此' }}
              </GameButton>
              <GameButton variant="ghost" @click="remove(model)">
                移除
              </GameButton>
            </div>
          </li>
        </ul>
      </GlassPanel>
    </div>
  </main>
</template>

<style scoped>
.settings-scene {
  min-height: calc(100vh - 2.5rem);
  padding: 1.25rem 1rem 2rem;
}

.settings-scene__container {
  max-width: 42rem;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.settings-scene__header {
  display: flex;
  align-items: flex-start;
  gap: 0.875rem;
  margin-bottom: 0.25rem;
}

.settings-scene__back {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
  text-decoration: none;
  padding: 0.5rem 0.625rem;
  border-radius: var(--radius-button);
  border: 1px solid var(--color-border);
  background: var(--color-bg-elevated);
  margin-top: 0.125rem;
  flex-shrink: 0;
  transition: color var(--motion-duration) var(--motion-ease);
}
.settings-scene__back:hover {
  color: var(--color-text-primary);
}

.settings-scene__title-area {
  min-width: 0;
}
.settings-scene__title {
  font-size: 1.35rem;
  font-weight: 700;
  color: var(--color-text-primary);
}
.settings-scene__subtitle {
  margin-top: 0.25rem;
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
}

/* 隐私声明 */
.privacy-block {
  padding: 0.25rem 0;
}
.privacy-block__title {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--color-text-primary);
  margin-bottom: 0.375rem;
}
.privacy-block__text {
  font-size: 0.8125rem;
  line-height: 1.6;
  color: var(--color-text-secondary);
}

/* section 标题 */
.section-heading {
  font-size: 0.9375rem;
  font-weight: 600;
  color: var(--color-text-primary);
  margin-bottom: 1rem;
}

/* 表单 */
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
  outline: none;
  transition: border-color var(--motion-duration) var(--motion-ease);
}
.settings-form__input:focus {
  border-color: var(--color-accent);
}
.settings-form__input::placeholder {
  color: var(--color-text-secondary);
  opacity: 0.6;
}
.settings-form__checkbox {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
  cursor: pointer;
}
.settings-form__checkbox input[type='checkbox'] {
  accent-color: var(--color-accent);
}
.settings-form__actions {
  display: flex;
  align-items: center;
  gap: 0.875rem;
  margin-top: 0.25rem;
}
.settings-form__msg {
  font-size: 0.8125rem;
}
.settings-form__msg--ok {
  color: var(--color-success);
}
.settings-form__msg--err {
  color: var(--color-danger);
}

/* 模型列表 */
.models-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
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
.models-list__info {
  min-width: 0;
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
  align-items: center;
  gap: 0.375rem;
  flex-shrink: 0;
}

.settings-scene__hint {
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
}
</style>