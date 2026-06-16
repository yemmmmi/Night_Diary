import { defineStore } from 'pinia'
import { ref } from 'vue'
import { isAxiosError } from 'axios'

import {
  deleteWeekly,
  generateWeekly,
  getLatestWeekly,
  listWeekly,
  regenerateWeekly,
  type WeeklyReport,
} from '@/shared/api/weekly'
import { formatApiError } from '@/shared/utils/apiError'

export const useWeeklyStore = defineStore('weekly', () => {
  const reports = ref<WeeklyReport[]>([])
  const latest = ref<WeeklyReport | null>(null)
  const loading = ref(false)
  const generating = ref(false)
  const deleting = ref(false)
  const error = ref<string | null>(null)

  async function loadReports(): Promise<WeeklyReport[]> {
    loading.value = true
    error.value = null
    try {
      reports.value = await listWeekly({ limit: 52 })
      latest.value = reports.value[0] ?? null
      return reports.value
    } catch (err) {
      error.value = formatApiError(err, '加载周记失败')
      throw err
    } finally {
      loading.value = false
    }
  }

  async function loadLatest(): Promise<WeeklyReport | null> {
    loading.value = true
    error.value = null
    try {
      latest.value = await getLatestWeekly()
      return latest.value
    } catch (err) {
      if (isAxiosError(err) && err.response?.status === 404) {
        latest.value = null
        return null
      }
      error.value = formatApiError(err, '加载周记失败')
      throw err
    } finally {
      loading.value = false
    }
  }

  function _upsert(report: WeeklyReport) {
    const idx = reports.value.findIndex((r) => r.period_start === report.period_start)
    if (idx >= 0) reports.value.splice(idx, 1, report)
    else reports.value.unshift(report)
    reports.value.sort((a, b) => b.period_start.localeCompare(a.period_start))
    latest.value = reports.value[0] ?? null
  }

  async function generate(): Promise<WeeklyReport> {
    generating.value = true
    error.value = null
    try {
      const report = await generateWeekly()
      _upsert(report)
      return report
    } catch (err) {
      error.value = formatApiError(err, '生成周记失败')
      throw err
    } finally {
      generating.value = false
    }
  }

  async function regenerate(): Promise<WeeklyReport> {
    generating.value = true
    error.value = null
    try {
      const report = await regenerateWeekly()
      _upsert(report)
      return report
    } catch (err) {
      error.value = formatApiError(err, '重新生成周记失败')
      throw err
    } finally {
      generating.value = false
    }
  }

  async function remove(reportId: number): Promise<void> {
    deleting.value = true
    error.value = null
    try {
      await deleteWeekly(reportId)
      reports.value = reports.value.filter((r) => r.id !== reportId)
      latest.value = reports.value[0] ?? null
    } catch (err) {
      error.value = formatApiError(err, '删除周记失败')
      throw err
    } finally {
      deleting.value = false
    }
  }

  return {
    reports,
    latest,
    loading,
    generating,
    deleting,
    error,
    loadReports,
    loadLatest,
    generate,
    regenerate,
    remove,
  }
})
