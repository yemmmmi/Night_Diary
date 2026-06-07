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
      path: '/settings',
      name: 'settings',
      component: SettingsScene,
    },
    {
      path: '/settings/llm',
      redirect: '/settings',
    },
  ],
})

export default router
