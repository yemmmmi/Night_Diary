import { defineStore } from 'pinia'
import { ref } from 'vue'

import {
  generateWeekly,
  listWeekly,
  regenerateWeekly,
  type WeeklyReport,
} from '@/shared/api/weekly'
import { formatApiError } from '@/shared/utils/apiError'

export const useWeeklyStore = defineStore('weekly', () => {
  const reports = ref<WeeklyReport[]>([])
  const loading = ref(false)
  const generating = ref(false)
  const error = ref<string | null>(null)

  async function loadReports(): Promise<WeeklyReport[]> {
    loading.value = true
    error.value = null
    try {
      reports.value = await listWeekly({ limit: 52 })
      return reports.value
    } catch (err) {
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

  return {
    reports,
    loading,
    generating,
    error,
    loadReports,
    generate,
    regenerate,
  }
})
