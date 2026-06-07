import { createApp } from 'vue'

import App from './App.vue'
import router from './router'
import { initTheme } from '@/shared/composables/useTheme'
import '@/styles/base.css'

initTheme()

createApp(App).use(router).mount('#app')
