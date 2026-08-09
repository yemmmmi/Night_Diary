import { defineStore } from 'pinia'
import { ref } from 'vue'
import * as planApi from '@/shared/api/plan'

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
    toggleTask,
    removeTask,
    removePlan,
  }
})
