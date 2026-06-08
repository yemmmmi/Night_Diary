import { defineStore } from 'pinia'
import { ref } from 'vue'

import {
  createDiaryEntry,
  deleteDiaryEntry,
  getDiaryEntry,
  listDiaryEntries,
  updateDiaryEntry,
  type DiaryCreatePayload,
  type DiaryEntry,
  type DiaryUpdatePayload,
} from '@/shared/api/diary'
import { formatApiError } from '@/shared/utils/apiError'

export const useDiaryStore = defineStore('diary', () => {
  const entries = ref<DiaryEntry[]>([])
  const currentEntry = ref<DiaryEntry | null>(null)
  const loading = ref(false)
  const saving = ref(false)
  const error = ref<string | null>(null)

  async function loadEntries(options: { skip?: number; limit?: number } = {}) {
    loading.value = true
    error.value = null
    try {
      entries.value = await listDiaryEntries({ skip: 0, limit: 100, ...options })
    } catch (err) {
      error.value = formatApiError(err, '加载日记失败')
      throw err
    } finally {
      loading.value = false
    }
  }

  async function fetchEntry(diaryId: number) {
    loading.value = true
    error.value = null
    try {
      currentEntry.value = await getDiaryEntry(diaryId)
      return currentEntry.value
    } catch (err) {
      error.value = formatApiError(err, '加载日记失败')
      throw err
    } finally {
      loading.value = false
    }
  }

  async function createEntry(payload: DiaryCreatePayload) {
    saving.value = true
    error.value = null
    try {
      const created = await createDiaryEntry(payload)
      entries.value = [created, ...entries.value.filter((e) => e.id !== created.id)]
      currentEntry.value = created
      return created
    } catch (err) {
      error.value = formatApiError(err, '保存日记失败')
      throw err
    } finally {
      saving.value = false
    }
  }

  async function saveEntry(diaryId: number, payload: DiaryUpdatePayload) {
    saving.value = true
    error.value = null
    try {
      const updated = await updateDiaryEntry(diaryId, payload)
      entries.value = entries.value.map((e) => (e.id === updated.id ? updated : e))
      if (currentEntry.value?.id === updated.id) {
        currentEntry.value = updated
      }
      return updated
    } catch (err) {
      error.value = formatApiError(err, '保存日记失败')
      throw err
    } finally {
      saving.value = false
    }
  }

  async function removeEntry(diaryId: number) {
    saving.value = true
    error.value = null
    try {
      await deleteDiaryEntry(diaryId)
      entries.value = entries.value.filter((e) => e.id !== diaryId)
      if (currentEntry.value?.id === diaryId) {
        currentEntry.value = null
      }
    } catch (err) {
      error.value = formatApiError(err, '删除日记失败')
      throw err
    } finally {
      saving.value = false
    }
  }

  function clearCurrent() {
    currentEntry.value = null
  }

  return {
    entries,
    currentEntry,
    loading,
    saving,
    error,
    loadEntries,
    fetchEntry,
    createEntry,
    saveEntry,
    removeEntry,
    clearCurrent,
  }
})
