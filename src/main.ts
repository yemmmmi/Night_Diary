import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'
import { bindSoundSettingWatcher } from '@/shared/composables/useSound'
import { initTheme } from '@/shared/composables/useTheme'
import { useSettingsStore } from '@/stores/settings'

/* 自托管字体（离线可用，按需加载） */
import '@fontsource/noto-serif-sc/chinese-simplified-400.css'
import '@fontsource/noto-serif-sc/chinese-simplified-600.css'
import '@fontsource/noto-serif-sc/chinese-simplified-700.css'
import '@fontsource/plus-jakarta-sans/index.css'
import 'lxgw-wenkai-webfont/lxgwwenkai-regular.css'
import 'lxgw-wenkai-webfont/lxgwwenkai-bold.css'

import '@/styles/base.css'

const pinia = createPinia()
const app = createApp(App).use(pinia)

useSettingsStore(pinia).load()
initTheme()
bindSoundSettingWatcher()

app.use(router).mount('#app')
