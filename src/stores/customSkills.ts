import { defineStore } from 'pinia'
import { ref } from 'vue'

import {
  createCustomSkill,
  deleteCustomSkill,
  listCustomSkills,
  setCustomSkillEnabled,
  updateCustomSkill,
  type CustomSkill,
  type CustomSkillInput,
} from '@/shared/api/customSkills'
import { customSkillsCopy } from '@/shared/copy/customSkills'
import { formatApiError } from '@/shared/utils/apiError'

export const useCustomSkillsStore = defineStore('customSkills', () => {
  const skills = ref<CustomSkill[]>([])
  const loading = ref(false)
  const saving = ref(false)
  const error = ref<string | null>(null)

  async function loadAll(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      skills.value = await listCustomSkills()
    } catch (err) {
      error.value = formatApiError(err, customSkillsCopy.loadError)
      throw err
    } finally {
      loading.value = false
    }
  }

  async function create(body: CustomSkillInput): Promise<void> {
    saving.value = true
    error.value = null
    try {
      const skill = await createCustomSkill(body)
      skills.value = [...skills.value, skill]
    } catch (err) {
      error.value = formatApiError(err, customSkillsCopy.createError)
      throw err
    } finally {
      saving.value = false
    }
  }

  async function update(id: number, body: CustomSkillInput): Promise<void> {
    saving.value = true
    error.value = null
    try {
      const skill = await updateCustomSkill(id, body)
      skills.value = skills.value.map((s) => (s.id === id ? skill : s))
    } catch (err) {
      error.value = formatApiError(err, customSkillsCopy.updateError)
      throw err
    } finally {
      saving.value = false
    }
  }

  async function toggle(id: number, enabled: boolean): Promise<void> {
    saving.value = true
    error.value = null
    try {
      const skill = await setCustomSkillEnabled(id, enabled)
      skills.value = skills.value.map((s) => (s.id === id ? skill : s))
    } catch (err) {
      error.value = formatApiError(err, customSkillsCopy.updateError)
      throw err
    } finally {
      saving.value = false
    }
  }

  async function remove(id: number): Promise<void> {
    saving.value = true
    error.value = null
    try {
      await deleteCustomSkill(id)
      skills.value = skills.value.filter((s) => s.id !== id)
    } catch (err) {
      error.value = formatApiError(err, customSkillsCopy.deleteError)
      throw err
    } finally {
      saving.value = false
    }
  }

  return { skills, loading, saving, error, loadAll, create, update, toggle, remove }
})