import { defineStore } from 'pinia'
import { ref } from 'vue'

import type { TraceSummary, PipelineTrace } from '@/shared/api/dev'

export const useDevStore = defineStore('dev', () => {
  const traceList = ref<TraceSummary[]>([])
  const currentTraceDetail = ref<PipelineTrace | null>(null)
  const activeTraceId = ref<string | null>(null)
  const total = ref(0)

  function setActiveTrace(traceId: string | null) {
    activeTraceId.value = traceId
    if (traceId) {
      localStorage.setItem('night-diary-active-trace-id', traceId)
    } else {
      localStorage.removeItem('night-diary-active-trace-id')
    }
  }

  function clearTraces() {
    traceList.value = []
    currentTraceDetail.value = null
  }

  return { traceList, currentTraceDetail, activeTraceId, total, setActiveTrace, clearTraces }
})
