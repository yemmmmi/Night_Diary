/// <reference types="vite/client" />

declare global {
  interface ImportMetaEnv {
    readonly VITE_API_BASE_URL?: string
  }

  interface ImportMeta {
    readonly env: ImportMetaEnv
  }

  interface Window {
    /** Electron preload 注入；桌面模式指向本地后端同源地址。 */
    __NIGHT_DIARY__?: { backendUrl?: string }
  }
}

export {}