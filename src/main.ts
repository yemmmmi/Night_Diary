import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'
import { initTheme } from '@/shared/composables/useTheme'
import '@/styles/base.css'

initTheme()

createApp(App).use(createPinia()).use(router).mount('#app')