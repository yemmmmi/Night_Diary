<script setup lang="ts">
import { computed } from 'vue'
import { PhMicrophone, PhMicrophoneSlash } from '@phosphor-icons/vue'

import { diarySceneCopy as copy } from '@/shared/copy/diaryScene'
import { isVoiceDictationSupported, useVoiceDictation } from '@/shared/composables/useVoiceDictation'

const props = withDefaults(defineProps<{ lang?: string }>(), { lang: 'zh-CN' })

const emit = defineEmits<{ transcript: [text: string] }>()

const supported = computed(() => isVoiceDictationSupported())

const { listening, toggle } = useVoiceDictation({
  lang: props.lang,
  onTranscript: (text) => emit('transcript', text),
})

const label = computed(() => {
  if (!supported.value) return copy.voiceUnsupported
  return listening.value ? copy.voiceStop : copy.voiceStart
})
</script>

<template>
  <button
    type="button"
    class="voice-dictation"
    :class="{ 'voice-dictation--active': listening }"
    :disabled="!supported"
    :title="label"
    :aria-label="label"
    data-testid="voice-dictation"
    @click="toggle"
  >
    <component :is="listening ? PhMicrophoneSlash : PhMicrophone" :size="15" />
    <span class="voice-dictation__label">{{ label }}</span>
  </button>
</template>

<style scoped>
.voice-dictation {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  background: none;
  border: none;
  padding: 0;
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
  cursor: pointer;
}
.voice-dictation:hover:not(:disabled) {
  color: var(--color-text-primary);
}
.voice-dictation:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.voice-dictation--active {
  color: var(--color-danger);
}
</style>