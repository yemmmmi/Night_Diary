import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'
import { bindSoundSettingWatcher } from '@/shared/composables/useSound'
import { initTheme } from '@/shared/composables/useTheme'
import { useSettingsStore } from '@/stores/settings'
import '@/styles/base.css'

const pinia = createPinia()
const app = createApp(App).use(pinia)

useSettingsStore(pinia).load()
initTheme()
bindSoundSettingWatcher()

app.use(router).mount('#app')
