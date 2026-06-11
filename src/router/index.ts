import { createRouter, createWebHashHistory } from 'vue-router'

import SettingsScene from '@/pages/SettingsScene.vue'

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
      path: '/design-system',
      name: 'design-system',
      component: () => import('@/pages/DesignSystemScene.vue'),
    },
    {
      path: '/settings',
      name: 'settings',
      component: SettingsScene,
    },
    {
      path: '/settings/llm',
      redirect: '/settings',
    },
    {
      path: '/analysis/:diaryId',
      name: 'analysis',
      component: () => import('@/pages/AnalysisScene.vue'),
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

export default router
