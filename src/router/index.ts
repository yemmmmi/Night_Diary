import { createRouter, createWebHashHistory } from 'vue-router'

import { listDiaryEntries } from '@/shared/api/diary'
import { waitForCoreReady } from '@/shared/composables/useBackend'
import SettingsScene from '@/pages/SettingsScene.vue'
import { useSettingsStore } from '@/stores/settings'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    {
      path: '/',
      name: 'home',
      component: () => import('@/pages/HomeScene.vue'),
    },
    {
      path: '/write',
      name: 'write-new',
      component: () => import('@/pages/DiaryScene.vue'),
    },
    {
      path: '/write/:id',
      name: 'write-edit',
      component: () => import('@/pages/DiaryScene.vue'),
    },
    {
      path: '/onboarding',
      name: 'onboarding',
      component: () => import('@/pages/OnboardingScene.vue'),
      meta: { skipOnboarding: true },
    },
    {
      path: '/settings',
      name: 'settings',
      component: SettingsScene,
      meta: { skipOnboarding: true },
    },
    {
      path: '/settings/llm',
      redirect: { path: '/settings', hash: '#llm' },
    },
    {
      path: '/settings/backup',
      redirect: { path: '/settings', hash: '#backup' },
    },
    {
      path: '/analysis/:diaryId',
      name: 'analysis',
      component: () => import('@/pages/AnalysisScene.vue'),
    },
    {
      path: '/weekly',
      name: 'weekly',
      component: () => import('@/pages/WeeklyScene.vue'),
    },
    {
      path: '/memory',
      name: 'memory',
      component: () => import('@/pages/MemoryScene.vue'),
    },
    {
      path: '/chat',
      name: 'chat',
      component: () => import('@/pages/ChatScene.vue'),
    },
    {
      path: '/review',
      name: 'review',
      component: () => import('@/pages/ReviewScene.vue'),
    },
    {
      path: '/review/:diaryId',
      name: 'review-detail',
      component: () => import('@/pages/ReviewScene.vue'),
    },
  ],
})

router.beforeEach(async (to) => {
  if (to.meta.skipOnboarding) return true

  const settings = useSettingsStore()
  settings.load()
  if (settings.onboardingCompleted) return true
  if (to.name === 'onboarding') return true

  try {
    await waitForCoreReady()
    const entries = await listDiaryEntries({ limit: 1 })
    if (entries.length > 0) {
      settings.completeOnboarding()
      return true
    }
  } catch {
    return true
  }

  return { name: 'onboarding' }
})

export default router
