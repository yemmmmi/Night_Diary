import { defineStore } from 'pinia'
import { ref } from 'vue'
import { isAxiosError } from 'axios'

import {
  deleteAnalysis,
  getAnalysis,
  regenerateAnalysis,
  triggerAnalysis,
  type AnalysisRecord,
} from '@/shared/api/analysis'
import { formatApiError } from '@/shared/utils/apiError'

export const useAnalysisStore = defineStore('analysis', () => {
  const current = ref<AnalysisRecord | null>(null)
  const loading = ref(false)
  const triggering = ref(false)
  const error = ref<string | null>(null)

  const deleting = ref(false)

  async function loadForDiary(diaryId: number): Promise<AnalysisRecord | null> {
    loading.value = true
    error.value = null
    try {
      current.value = await getAnalysis(diaryId)
      return current.value
    } catch (err) {
      if (isAxiosError(err) && err.response?.status === 404) {
        current.value = null
        return null
      }
      error.value = formatApiError(err, '加载分析结果失败')
      throw err
    } finally {
      loading.value = false
    }
  }

  async function triggerForDiary(diaryId: number): Promise<AnalysisRecord> {
    triggering.value = true
    error.value = null
    try {
      current.value = await triggerAnalysis(diaryId)
      return current.value
    } catch (err) {
      error.value = formatApiError(err, 'AI 分析失败')
      throw err
    } finally {
      triggering.value = false
    }
  }

  async function regenerateForDiary(diaryId: number): Promise<AnalysisRecord> {
    triggering.value = true
    error.value = null
    try {
      current.value = await regenerateAnalysis(diaryId)
      return current.value
    } catch (err) {
      error.value = formatApiError(err, '重新生成回信失败')
      throw err
    } finally {
      triggering.value = false
    }
  }

  async function removeForDiary(diaryId: number): Promise<void> {
    deleting.value = true
    error.value = null
    try {
      await deleteAnalysis(diaryId)
      current.value = null
    } catch (err) {
      error.value = formatApiError(err, '删除回信失败')
      throw err
    } finally {
      deleting.value = false
    }
  }

  function clear() {
    current.value = null
    error.value = null
  }

  return {
    current,
    loading,
    triggering,
    deleting,
    error,
    loadForDiary,
    triggerForDiary,
    regenerateForDiary,
    removeForDiary,
    clear,
  }
})
