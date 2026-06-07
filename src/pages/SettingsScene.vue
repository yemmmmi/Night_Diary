<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'

import {
  createModel,
  deleteModel,
  listModels,
  updateModel,
  type ModelProvider,
  type ModelTier,
} from '@/shared/api/models'

const tiers: ModelTier[] = ['light', 'medium', 'heavy', 'default']

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
  if (!window.confirm(`删除模型「${model.model_name}」？`)) return
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
  <div class="min-h-screen bg-slate-50 text-slate-900">
    <header class="border-b border-slate-200 bg-white px-6 py-4 flex items-center justify-between">
      <div>
        <h1 class="text-xl font-semibold">LLM 配置</h1>
        <p class="text-sm text-slate-500">为 light / medium / heavy 分别配置模型</p>
      </div>
      <RouterLink to="/" class="text-sm text-slate-600 hover:text-slate-900">返回首页</RouterLink>
    </header>

    <div class="mx-auto max-w-3xl px-6 py-8 space-y-8">
      <section class="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 class="text-lg font-medium mb-4">添加模型</h2>
        <form class="grid gap-4 sm:grid-cols-2" @submit.prevent="submit">
          <label class="block text-sm">
            <span class="text-slate-600">模型名称</span>
            <input
              v-model="form.model_name"
              required
              class="mt-1 w-full rounded border border-slate-300 px-3 py-2"
              placeholder="deepseek-chat"
            />
          </label>
          <label class="block text-sm">
            <span class="text-slate-600">Tier</span>
            <select v-model="form.tier" class="mt-1 w-full rounded border border-slate-300 px-3 py-2">
              <option v-for="tier in tiers" :key="tier" :value="tier">{{ tier }}</option>
            </select>
          </label>
          <label class="block text-sm sm:col-span-2">
            <span class="text-slate-600">Base URL</span>
            <input
              v-model="form.base_url"
              required
              class="mt-1 w-full rounded border border-slate-300 px-3 py-2"
              placeholder="https://api.deepseek.com/v1"
            />
          </label>
          <label class="block text-sm sm:col-span-2">
            <span class="text-slate-600">API Key</span>
            <input
              v-model="form.api_key"
              required
              type="password"
              class="mt-1 w-full rounded border border-slate-300 px-3 py-2"
              placeholder="sk-..."
            />
          </label>
          <label class="flex items-center gap-2 text-sm sm:col-span-2">
            <input v-model="form.is_active" type="checkbox" />
            <span>设为该 tier 的启用模型</span>
          </label>
          <div class="sm:col-span-2">
            <button
              type="submit"
              :disabled="saving"
              class="rounded-lg bg-slate-900 px-4 py-2 text-sm text-white disabled:opacity-50"
            >
              {{ saving ? '保存中…' : '保存' }}
            </button>
          </div>
        </form>
        <p v-if="success" class="mt-3 text-sm text-green-700">{{ success }}</p>
        <p v-if="error" class="mt-3 text-sm text-red-600">{{ error }}</p>
      </section>

      <section class="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 class="text-lg font-medium mb-4">已配置模型</h2>
        <p v-if="loading" class="text-sm text-slate-500">加载中…</p>
        <p v-else-if="models.length === 0" class="text-sm text-slate-500">暂无模型，请先添加。</p>
        <ul v-else class="divide-y divide-slate-100">
          <li
            v-for="model in models"
            :key="model.id"
            class="flex flex-wrap items-center justify-between gap-3 py-3"
          >
            <div>
              <p class="font-medium">{{ model.model_name }}</p>
              <p class="text-sm text-slate-500">
                tier={{ model.tier }} · {{ model.base_url || '无 base_url' }}
                · {{ model.has_api_key ? '已配置 Key' : '无 Key' }}
              </p>
            </div>
            <div class="flex items-center gap-2">
              <button
                type="button"
                class="rounded border border-slate-300 px-3 py-1 text-sm"
                @click="toggleActive(model)"
              >
                {{ model.is_active ? '已启用' : '启用' }}
              </button>
              <button
                type="button"
                class="rounded border border-red-200 px-3 py-1 text-sm text-red-700"
                @click="remove(model)"
              >
                删除
              </button>
            </div>
          </li>
        </ul>
      </section>
    </div>
  </div>
</template>
