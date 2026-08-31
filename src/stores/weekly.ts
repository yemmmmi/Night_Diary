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
  /** 最近一次 loadReports 实际拉取的条数（洞悉页只装最近几封时小于 52）。 */
  const loadedLimit = ref<number | null>(null)
  const loading = ref(false)
  const generating = ref(false)
  const error = ref<string | null>(null)

  async function loadReports(limit: number = 52): Promise<WeeklyReport[]> {
    loading.value = true
    error.value = null
    try {
      reports.value = await listWeekly({ limit })
      loadedLimit.value = limit
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
    loadedLimit,
    loading,
    generating,
    error,
    loadReports,
    generate,
    regenerate,
  }
})
