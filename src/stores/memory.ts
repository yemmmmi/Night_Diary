import { defineStore } from 'pinia'
import { ref } from 'vue'

import {
  getOverview,
  getProfile,
  listEpisodic,
  type EpisodicEntry,
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

  return {
    episodic,
    profile,
    overview,
    loading,
    error,
    loadAll,
  }
})
