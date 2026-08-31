import { defineStore } from 'pinia'
import { ref } from 'vue'
import * as planApi from '@/shared/api/plan'
import { toIsoDate } from '@/shared/utils/diaryFormat'

export const usePlanStore = defineStore('plan', () => {
  const plans = ref<planApi.PlanItem[]>([])
  const todayTasks = ref<planApi.TaskItem[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function loadPlans() {
    loading.value = true
    error.value = null
    try {
      plans.value = await planApi.listPlans()
    } catch {
      error.value = '加载计划失败'
    } finally {
      loading.value = false
    }
  }

  async function loadTodayTasks() {
    try {
      todayTasks.value = await planApi.getTodayTasks()
    } catch {
      error.value = '加载今日待办失败'
    }
  }

  async function createPlan(payload: {
    title: string
    motivation?: string
    tasks?: Array<{ title: string; note?: string; due_date?: string }>
    recurrence?: string
    target_value?: number
    target_unit?: string
    target_period?: 'daily' | 'weekly' | 'total'
  }) {
    error.value = null
    try {
      await planApi.createPlan({ ...payload, source: 'manual' })
      await loadPlans()
      await loadTodayTasks()
      return true
    } catch {
      error.value = '创建计划失败'
      return false
    }
  }

  async function createTodayTask(title: string, dueDate: string | null) {
    error.value = null
    try {
      await planApi.createTask({ title, due_date: dueDate ?? undefined })
      await loadTodayTasks()
      await loadPlans()
      return true
    } catch {
      error.value = '创建待办失败'
      return false
    }
  }

  async function toggleTask(taskId: string, currentStatus: string) {
    const newStatus = currentStatus === 'done' ? 'pending' : 'done'
    try {
      await planApi.updateTaskStatus(taskId, newStatus as 'pending' | 'done')
      await loadTodayTasks()
      await loadPlans()
    } catch {
      error.value = '更新任务失败'
    }
  }

  /** 完成任务并记录实际值（§6.3：无值按 1 次计数由聚合兜底）。 */
  async function completeTask(taskId: string, actualValue?: number) {
    error.value = null
    try {
      await planApi.updateTaskStatus(taskId, 'done', actualValue)
      await loadTodayTasks()
      await loadPlans()
    } catch {
      error.value = '更新任务失败'
    }
  }

  /** 从活跃计划手动拉一条进今日待办（§6.3 手动拉取，预填标题可改）。 */
  async function pullToToday(planId: string, title: string) {
    error.value = null
    try {
      await planApi.createTask({
        plan_id: planId,
        title,
        due_date: toIsoDate(new Date()),
      })
      await loadTodayTasks()
      await loadPlans()
      return true
    } catch {
      error.value = '创建待办失败'
      return false
    }
  }

  async function removeTask(taskId: string) {
    try {
      await planApi.deleteTask(taskId)
      await loadTodayTasks()
      await loadPlans()
    } catch {
      error.value = '删除任务失败'
    }
  }

  async function removePlan(planId: string) {
    try {
      await planApi.deletePlan(planId)
      await loadPlans()
    } catch {
      error.value = '删除计划失败'
    }
  }

  return {
    plans,
    todayTasks,
    loading,
    error,
    loadPlans,
    loadTodayTasks,
    createPlan,
    createTodayTask,
    toggleTask,
    completeTask,
    pullToToday,
    removeTask,
    removePlan,
  }
})
