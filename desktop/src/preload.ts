import { contextBridge } from 'electron'

// 注意：沙箱（sandbox: true）下的 preload 只能 require electron 白名单模块，
// 不能 require 任何本地文件（如 ./argv），否则整个 preload 会加载失败。
// 因此参数解析必须内联在本文件中，保持 preload 为单文件。
const BACKEND_URL_PREFIX = '--backend-url='

function parseBackendUrl(argv: string[]): string | undefined {
  const hit = argv.find((arg) => arg.startsWith(BACKEND_URL_PREFIX))
  return hit ? hit.slice(BACKEND_URL_PREFIX.length) : undefined
}

const backendUrl = parseBackendUrl(process.argv)

if (backendUrl) {
  contextBridge.exposeInMainWorld('__NIGHT_DIARY__', { backendUrl })
}