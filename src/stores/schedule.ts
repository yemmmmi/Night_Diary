import { defineStore } from 'pinia'
import { ref } from 'vue'

import {
  createSchedule,
  deleteSchedule,
  listKinds,
  listRuns,
  listSchedules,
  triggerSchedule,
  updateSchedule,
  type ScheduledTask,
  type ScheduledTaskCreate,
  type ScheduledTaskKind,
  type ScheduledTaskRun,
  type ScheduledTaskUpdate,
} from '@/shared/api/schedule'
import { formatApiError } from '@/shared/utils/apiError'
import { scheduleCopy } from '@/shared/copy/schedule'

export const useScheduleStore = defineStore('schedule', () => {
  const tasks = ref<ScheduledTask[]>([])
  const kinds = ref<ScheduledTaskKind[]>([])
  const runs = ref<Record<string, ScheduledTaskRun[]>>({})
  const loading = ref(false)
  const saving = ref(false)
  const error = ref<string | null>(null)

  async function loadAll(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const [ks, ts] = await Promise.all([listKinds(), listSchedules()])
      kinds.value = ks
      tasks.value = ts
    } catch (err) {
      error.value = formatApiError(err, scheduleCopy.loadError)
      throw err
    } finally {
      loading.value = false
    }
  }

  async function create(body: ScheduledTaskCreate): Promise<void> {
    saving.value = true
    error.value = null
    try {
      const task = await createSchedule(body)
      tasks.value = [...tasks.value, task]
    } catch (err) {
      error.value = formatApiError(err, scheduleCopy.createError)
      throw err
    } finally {
      saving.value = false
    }
  }

  async function update(id: string, patch: ScheduledTaskUpdate): Promise<void> {
    saving.value = true
    error.value = null
    try {
      const task = await updateSchedule(id, patch)
      tasks.value = tasks.value.map((t) => (t.id === id ? task : t))
    } catch (err) {
      error.value = formatApiError(err, scheduleCopy.updateError)
      throw err
    } finally {
      saving.value = false
    }
  }

  async function remove(id: string): Promise<void> {
    saving.value = true
    error.value = null
    try {
      await deleteSchedule(id)
      tasks.value = tasks.value.filter((t) => t.id !== id)
      const next = { ...runs.value }
      delete next[id]
      runs.value = next
    } catch (err) {
      error.value = formatApiError(err, scheduleCopy.deleteError)
      throw err
    } finally {
      saving.value = false
    }
  }

  async function trigger(id: string): Promise<void> {
    saving.value = true
    error.value = null
    try {
      const task = await triggerSchedule(id)
      tasks.value = tasks.value.map((t) => (t.id === id ? task : t))
    } catch (err) {
      error.value = formatApiError(err, scheduleCopy.triggerError)
      throw err
    } finally {
      saving.value = false
    }
  }

  async function loadRuns(id: string, limit = 20): Promise<void> {
    error.value = null
    try {
      runs.value = { ...runs.value, [id]: await listRuns(id, limit) }
    } catch (err) {
      error.value = formatApiError(err, scheduleCopy.loadError)
      throw err
    }
  }

  return {
    tasks,
    kinds,
    runs,
    loading,
    saving,
    error,
    loadAll,
    create,
    update,
    remove,
    trigger,
    loadRuns,
  }
})