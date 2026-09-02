import { createRouter, createWebHashHistory, type RouteMeta, type RouteRecordRaw } from 'vue-router'

import { listDiaryEntries } from '@/shared/api/diary'
import { waitForCoreReady } from '@/shared/composables/useBackend'
import SettingsScene from '@/pages/SettingsScene.vue'
import { useSettingsStore } from '@/stores/settings'

declare module 'vue-router' {
  interface RouteMeta {
    /** 公开路由：无需登录即可访问 */
    public?: boolean
    /** 跳过 onboarding 引导检查 */
    skipOnboarding?: boolean
  }
}

// 确保 RouteMeta 类型增强被引用，避免被 tree-shake 移除
export type AppRouteMeta = RouteMeta

export const appRoutes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/pages/LoginScene.vue'),
    meta: { public: true, skipOnboarding: true },
  },
  {
    path: '/',
    name: 'home',
    redirect: { name: 'timeline' },
  },
  {
    path: '/timeline',
    name: 'timeline',
    component: () => import('@/pages/TimelineScene.vue'),
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
    redirect: { name: 'models' },
  },
  {
    path: '/settings/backup',
    redirect: { path: '/settings', hash: '#backup' },
  },
  {
    path: '/weekly',
    redirect: { path: '/timeline', query: { view: 'week' } },
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
    path: '/plan',
    name: 'plan',
    component: () => import('@/features/plan/PlanScene.vue'),
  },
  {
    path: '/models',
    name: 'models',
    component: () => import('@/pages/ModelsScene.vue'),
    meta: { skipOnboarding: true },
  },
  {
    path: '/review',
    redirect: { path: '/memory' },
  },
  {
    path: '/review/:diaryId',
    redirect: (to) => ({ path: `/write/${to.params.diaryId}` }),
  },
  {
    path: '/dev',
    name: 'dev',
    component: () => import('@/pages/DevScene.vue'),
    meta: { skipOnboarding: true },
  },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes: appRoutes,
})

router.beforeEach(async (to) => {
  // 认证检查：非 public 路由需要登录
  const token = localStorage.getItem('night_diary_token')
  if (!to.meta.public && !token) {
    return { name: 'login' }
  }
  // 已登录用户访问 login 页则跳转首页
  if (to.name === 'login' && token) {
    return { name: 'timeline' }
  }

  // 以下保留现有的 onboarding 逻辑
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
