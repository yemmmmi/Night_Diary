<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { openaiAccessCopy as copy } from '@/shared/copy/openaiAccess'
import { resolveBackendBaseUrl } from '@/shared/composables/useBackend'

defineOptions({ name: 'OpenAIAccessPanel' })

const chatEndpoint = ref('')
const modelsEndpoint = ref('')
const copied = ref('')

function joinBase(base: string, path: string): string {
  return `${base.replace(/\/+$/, '')}${path}`
}

async function copyText(value: string, key: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(value)
    copied.value = key
    setTimeout(() => {
      if (copied.value === key) copied.value = ''
    }, 1500)
  } catch {
    // clipboard unavailable — the URL stays selectable
  }
}

onMounted(async () => {
  const base = await resolveBackendBaseUrl()
  chatEndpoint.value = joinBase(base, '/v1/chat/completions')
  modelsEndpoint.value = joinBase(base, '/v1/models')
})
</script>

<template>
  <div class="openai-access">
    <p class="openai-access__intro">{{ copy.intro }}</p>

    <dl class="openai-access__list">
      <div class="openai-access__row">
        <dt>{{ copy.chatLabel }}</dt>
        <dd>
          <code data-testid="openai-chat-endpoint">{{ chatEndpoint }}</code>
          <button
            type="button"
            data-testid="openai-copy-chat"
            class="openai-access__copy"
            @click="copyText(chatEndpoint, 'chat')"
          >
            {{ copied === 'chat' ? copy.copied : copy.copy }}
          </button>
        </dd>
      </div>
      <div class="openai-access__row">
        <dt>{{ copy.modelsLabel }}</dt>
        <dd>
          <code data-testid="openai-models-endpoint">{{ modelsEndpoint }}</code>
          <button
            type="button"
            data-testid="openai-copy-models"
            class="openai-access__copy"
            @click="copyText(modelsEndpoint, 'models')"
          >
            {{ copied === 'models' ? copy.copied : copy.copy }}
          </button>
        </dd>
      </div>
    </dl>

    <p class="openai-access__hint">{{ copy.authHint }}</p>
    <p class="openai-access__hint">{{ copy.featureHint }}</p>
  </div>
</template>

<style scoped>
.openai-access {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.openai-access__intro {
  font-size: 0.8125rem;
  line-height: 1.7;
  color: var(--color-text-secondary);
}

.openai-access__list {
  display: flex;
  flex-direction: column;
  margin: 0;
}

.openai-access__row {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  padding: 0.5rem 0.125rem;
  border-top: 1px solid var(--color-line);
}

.openai-access__row dt {
  font-size: 0.75rem;
  color: var(--color-text-secondary);
}

.openai-access__row dd {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin: 0;
}

.openai-access__row code {
  font-size: 0.8125rem;
  color: var(--color-text-primary);
  word-break: break-all;
}

.openai-access__copy {
  flex-shrink: 0;
  background: none;
  border: none;
  padding: 0;
  font-size: 0.75rem;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: color var(--dur-fast) var(--ease-out-quart);
}

.openai-access__copy:hover {
  color: var(--color-accent);
}

.openai-access__hint {
  font-size: 0.75rem;
  line-height: 1.6;
  color: var(--color-text-faint);
}
</style>