import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'

import type { ThemePreference } from '@/shared/composables/useTheme'

const STORAGE_KEY = 'night-diary-app-settings'

export type ReplierPreset = 'warm' | 'pragmatic' | 'calm'

export interface SystemReplier {
  id: string
  type: 'system'
  name: string
  persona: string
}

export interface UserReplier {
  id: string
  type: 'user'
  name: string
  persona: string
}

export type ReplierConfig = SystemReplier | UserReplier

export const PRESET_REPLIERS: SystemReplier[] = [
  {
    id: 'preset-warm',
    type: 'system',
    name: '温暖',
    persona: '以温暖共情的方式回信，让用户感到被理解和接纳。语言柔和，不评价不分析，像一位耐心的倾听者',
  },
  {
    id: 'preset-pragmatic',
    type: 'system',
    name: '务实',
    persona: '简洁直接，就事论事。在表达理解的同时给出具体可操作的建议，像老朋友一样坦诚',
  },
  {
    id: 'preset-calm',
    type: 'system',
    name: '平静',
    persona: '温和从容。用"没关系，慢慢来"的节奏回应，先接纳再引导，不催促不安慰过度',
  },
]

const DEFAULT_ACTIVE_REPLIER_ID = 'preset-warm'

/** Look up a replier by id across system presets and user repliers. */
export function resolveReplier(
  userRepliers: UserReplier[],
  activeId: string,
): ReplierConfig | null {
  const preset = PRESET_REPLIERS.find((p) => p.id === activeId)
  if (preset) return preset
  return userRepliers.find((u) => u.id === activeId) ?? null
}

/** Whether the currently active replier has a user-set name (not a system preset). */
export function replierHasNickname(replier: ReplierConfig | null): boolean {
  if (!replier) return false
  return replier.type === 'user' && replier.name.trim().length > 0
}

export interface AppSettingsSnapshot {
  nickname: string
  themePreference: ThemePreference
  soundEnabled: boolean
  autoBackup: boolean
  onboardingCompleted: boolean
  activeReplierId: string
  userRepliers: UserReplier[]
}

const DEFAULTS: AppSettingsSnapshot = {
  nickname: '',
  themePreference: 'auto',
  soundEnabled: false,
  autoBackup: false,
  onboardingCompleted: false,
  activeReplierId: DEFAULT_ACTIVE_REPLIER_ID,
  userRepliers: [],
}

function validReplierId(parsed: Partial<AppSettingsSnapshot>): string {
  const id = parsed.activeReplierId
  if (typeof id !== 'string') return DEFAULT_ACTIVE_REPLIER_ID
  if (PRESET_REPLIERS.some((p) => p.id === id)) return id
  const users = Array.isArray(parsed.userRepliers) ? parsed.userRepliers : []
  if (users.some((u) => u.id === id)) return id
  return DEFAULT_ACTIVE_REPLIER_ID
}

function validUserRepliers(parsed: Partial<AppSettingsSnapshot>): UserReplier[] {
  if (!Array.isArray(parsed.userRepliers)) return []
  return parsed.userRepliers.filter(
    (u) => typeof u.id === 'string' && typeof u.name === 'string' && typeof u.persona === 'string',
  )
}

function readStored(): AppSettingsSnapshot {
  if (typeof window === 'undefined') return { ...DEFAULTS }
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return { ...DEFAULTS }
    const parsed = JSON.parse(raw) as Partial<AppSettingsSnapshot>
    return {
      nickname: typeof parsed.nickname === 'string' ? parsed.nickname : DEFAULTS.nickname,
      themePreference:
        parsed.themePreference === 'day' ||
        parsed.themePreference === 'night' ||
        parsed.themePreference === 'auto'
          ? parsed.themePreference
          : DEFAULTS.themePreference,
      soundEnabled: Boolean(parsed.soundEnabled),
      autoBackup: Boolean(parsed.autoBackup),
      onboardingCompleted: Boolean(parsed.onboardingCompleted),
      activeReplierId: validReplierId(parsed),
      userRepliers: validUserRepliers(parsed),
    }
  } catch {
    return { ...DEFAULTS }
  }
}

let _nextUserReplierId = 0
function generateReplierId(): string {
  _nextUserReplierId += 1
  return `user-replier-${Date.now()}-${_nextUserReplierId}`
}

export const useSettingsStore = defineStore('settings', () => {
  const loaded = ref(false)
  const nickname = ref(DEFAULTS.nickname)
  const themePreference = ref<ThemePreference>(DEFAULTS.themePreference)
  const soundEnabled = ref(DEFAULTS.soundEnabled)
  const autoBackup = ref(DEFAULTS.autoBackup)
  const onboardingCompleted = ref(DEFAULTS.onboardingCompleted)
  const activeReplierId = ref(DEFAULTS.activeReplierId)
  const userRepliers = ref<UserReplier[]>(DEFAULTS.userRepliers)

  const activeReplier = computed<ReplierConfig | null>(() =>
    resolveReplier(userRepliers.value, activeReplierId.value),
  )

  const replierName = computed(() => activeReplier.value?.name ?? '')

  const replierHasName = computed(() => replierHasNickname(activeReplier.value))

  const replierPersona = computed(() => activeReplier.value?.persona ?? '')

  const replierPreset = computed<ReplierPreset | null>(() => {
    const r = activeReplier.value
    if (!r || r.type !== 'system') return null
    if (r.id === 'preset-warm') return 'warm'
    if (r.id === 'preset-pragmatic') return 'pragmatic'
    if (r.id === 'preset-calm') return 'calm'
    return null
  })

  function applySnapshot(snapshot: AppSettingsSnapshot) {
    nickname.value = snapshot.nickname
    themePreference.value = snapshot.themePreference
    soundEnabled.value = snapshot.soundEnabled
    autoBackup.value = snapshot.autoBackup
    onboardingCompleted.value = snapshot.onboardingCompleted
    activeReplierId.value = snapshot.activeReplierId
    userRepliers.value = snapshot.userRepliers
  }

  function load() {
    if (loaded.value) return
    applySnapshot(readStored())
    loaded.value = true
  }

  function persist() {
    const snapshot: AppSettingsSnapshot = {
      nickname: nickname.value,
      themePreference: themePreference.value,
      soundEnabled: soundEnabled.value,
      autoBackup: autoBackup.value,
      onboardingCompleted: onboardingCompleted.value,
      activeReplierId: activeReplierId.value,
      userRepliers: userRepliers.value,
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(snapshot))
  }

  function completeOnboarding() {
    onboardingCompleted.value = true
    persist()
  }

  /** Switch to a system preset or user replier by id. */
  function setActiveReplier(id: string) {
    activeReplierId.value = id
    persist()
  }

  /** Create a new user-defined replier. */
  function addUserReplier(name: string, persona: string): UserReplier {
    const replier: UserReplier = {
      id: generateReplierId(),
      type: 'user',
      name,
      persona,
    }
    userRepliers.value = [...userRepliers.value, replier]
    activeReplierId.value = replier.id
    persist()
    return replier
  }

  /** Update an existing user replier. Returns false if not found. */
  function updateUserReplier(id: string, name: string, persona: string): boolean {
    const idx = userRepliers.value.findIndex((u) => u.id === id)
    if (idx === -1) return false
    userRepliers.value = [
      ...userRepliers.value.slice(0, idx),
      { id, type: 'user' as const, name, persona },
      ...userRepliers.value.slice(idx + 1),
    ]
    persist()
    return true
  }

  /** Delete a user replier. If it was active, fall back to default preset. */
  function deleteUserReplier(id: string): boolean {
    const idx = userRepliers.value.findIndex((u) => u.id === id)
    if (idx === -1) return false
    userRepliers.value = [
      ...userRepliers.value.slice(0, idx),
      ...userRepliers.value.slice(idx + 1),
    ]
    if (activeReplierId.value === id) {
      activeReplierId.value = DEFAULT_ACTIVE_REPLIER_ID
    }
    persist()
    return true
  }

  watch(
    [
      nickname,
      themePreference,
      soundEnabled,
      autoBackup,
      onboardingCompleted,
      activeReplierId,
      userRepliers,
    ],
    persist,
    { deep: true },
  )

  return {
    loaded,
    nickname,
    themePreference,
    soundEnabled,
    autoBackup,
    onboardingCompleted,
    activeReplierId,
    userRepliers,
    activeReplier,
    replierName,
    replierHasName,
    replierPersona,
    replierPreset,
    load,
    persist,
    completeOnboarding,
    setActiveReplier,
    addUserReplier,
    updateUserReplier,
    deleteUserReplier,
  }
})
