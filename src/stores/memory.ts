import { defineStore } from 'pinia'
import { ref } from 'vue'

import {
  getOverview,
  getProfile,
  listEpisodic,
  updateEpisodic,
  deleteEpisodic,
  type EpisodicEntry,
  type EpisodicEntryUpdate,
  type MemoryOverview,
  type UserProfile,
} from '@/shared/api/memory'
import { formatApiError } from '@/shared/utils/apiError'
import { memoryCopy } from '@/shared/copy/memory'

export const useMemoryStore = defineStore('memory', () => {
  const episodic = ref<EpisodicEntry[]>([])
  const profile = ref<UserProfile | null>(null)
  const overview = ref<MemoryOverview | null>(null)
  const loading = ref(false)
  const saving = ref(false)
  const error = ref<string | null>(null)

  async function loadAll(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const [ep, pr, ov] = await Promise.all([
        listEpisodic(),
        getProfile(),
        getOverview(),
      ])
      episodic.value = ep
      profile.value = pr
      overview.value = ov
    } catch (err) {
      error.value = formatApiError(err, memoryCopy.loadError)
      throw err
    } finally {
      loading.value = false
    }
  }

  async function saveEpisodic(entryId: string, patch: EpisodicEntryUpdate): Promise<void> {
    saving.value = true
    error.value = null
    try {
      const updated = await updateEpisodic(entryId, patch)
      episodic.value = episodic.value.map((e) =>
        e.entry_id === entryId ? updated : e,
      )
      overview.value = await getOverview()
    } catch (err) {
      error.value = formatApiError(err, memoryCopy.saveError)
      throw err
    } finally {
      saving.value = false
    }
  }

  async function removeEpisodic(entryId: string): Promise<void> {
    saving.value = true
    error.value = null
    try {
      await deleteEpisodic(entryId)
      episodic.value = episodic.value.filter((e) => e.entry_id !== entryId)
      overview.value = await getOverview()
    } catch (err) {
      error.value = formatApiError(err, memoryCopy.deleteError)
      throw err
    } finally {
      saving.value = false
    }
  }

  return {
    episodic,
    profile,
    overview,
    loading,
    saving,
    error,
    loadAll,
    saveEpisodic,
    removeEpisodic,
  }
})
