import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { getMoodTrends, type MoodTrendPoint } from '@/shared/api/card'
import { listDiaryEntries, type DiaryEntry } from '@/shared/api/diary'
import { listTasks, type TaskItem } from '@/shared/api/plan'
import { formatApiError } from '@/shared/utils/apiError'
import {
  endOfWeekSunday,
  parseLocalDate,
  startOfWeekMonday,
  toIsoDate,
} from '@/shared/utils/diaryFormat'
import type { TimelineView } from '@/shared/utils/timelineQuery'

export const useTimelineStore = defineStore('timeline', () => {
  // ── State ─────────────────────────────────────────────────────
  const view = ref<TimelineView>('day')
  const date = ref(toIsoDate(new Date()))
  const loading = ref(false)
  const error = ref<string | null>(null)

  const entries = ref<DiaryEntry[]>([])
  const tasks = ref<TaskItem[]>([])
  const moodTrend = ref<MoodTrendPoint[]>([])
  const selectedEntryId = ref<number | null>(null)

  // ── Getters ───────────────────────────────────────────────────
  const todayIso = computed(() => toIsoDate(new Date()))
  const isToday = computed(() => date.value === todayIso.value)
  const weekStart = computed(() => startOfWeekMonday(parseLocalDate(date.value)))
  const weekEnd = computed(() => endOfWeekSunday(weekStart.value))
  const weekStartIso = computed(() => toIsoDate(weekStart.value))
  const weekEndIso = computed(() => toIsoDate(weekEnd.value))

  const range = computed<{ from: string; to: string }>(() => {
    if (view.value === 'day') return { from: date.value, to: date.value }
    if (view.value === 'week') return { from: weekStartIso.value, to: weekEndIso.value }
    const anchor = parseLocalDate(date.value)
    return {
      from: toIsoDate(new Date(anchor.getFullYear(), anchor.getMonth(), 1)),
      to: toIsoDate(new Date(anchor.getFullYear(), anchor.getMonth() + 1, 0)),
    }
  })

  const selectedEntry = computed(() =>
    selectedEntryId.value == null
      ? null
      : entries.value.find((e) => e.id === selectedEntryId.value) ?? null,
  )

  // ── Actions ───────────────────────────────────────────────────
  async function load() {
    loading.value = true
    error.value = null
    const { from, to } = range.value
    try {
      if (view.value === 'week') {
        const [entryRows, taskRows, trendRows] = await Promise.all([
          listDiaryEntries({ date_from: from, date_to: to, limit: 100 }),
          listTasks({ date_from: from, date_to: to }),
          getMoodTrends({ date_from: from, date_to: to }).catch(() => []),
        ])
        entries.value = entryRows
        tasks.value = taskRows
        moodTrend.value = trendRows
      } else {
        entries.value = await listDiaryEntries({ date_from: from, date_to: to, limit: 100 })
        tasks.value = []
        moodTrend.value = []
      }
    } catch (err) {
      error.value = formatApiError(err, '加载日记失败')
    } finally {
      loading.value = false
    }
  }

  async function setView(next: TimelineView) {
    if (view.value === next) return
    view.value = next
    await load()
  }

  async function setDate(iso: string) {
    date.value = iso
    await load()
  }

  async function shiftPeriod(delta: number) {
    if (view.value === 'day') {
      const next = parseLocalDate(date.value)
      next.setDate(next.getDate() + delta)
      await setDate(toIsoDate(next))
      return
    }
    if (view.value === 'week') {
      await setDate(toIsoDate(startOfWeekMonday(parseLocalDate(date.value), delta)))
      return
    }
    const anchor = parseLocalDate(date.value)
    await setDate(toIsoDate(new Date(anchor.getFullYear(), anchor.getMonth() + delta, 1)))
  }

  async function goToday() {
    await setDate(todayIso.value)
  }

  function selectEntry(entryId: number | null) {
    selectedEntryId.value = entryId
  }

  return {
    view,
    date,
    loading,
    error,
    entries,
    tasks,
    moodTrend,
    selectedEntryId,
    todayIso,
    isToday,
    weekStart,
    weekEnd,
    weekStartIso,
    weekEndIso,
    range,
    selectedEntry,
    load,
    setView,
    setDate,
    shiftPeriod,
    goToday,
    selectEntry,
  }
})
