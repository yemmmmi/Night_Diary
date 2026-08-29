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

  async function createPlan(payload: {
    title: string
    motivation?: string
    tasks?: Array<{ title: string; note?: string; due_date?: string }>
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
    removeTask,
    removePlan,
  }
})
