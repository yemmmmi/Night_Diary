import { contextBridge } from 'electron'

import { parseBackendUrl } from './argv'

const backendUrl = parseBackendUrl(process.argv)

if (backendUrl) {
  contextBridge.exposeInMainWorld('__NIGHT_DIARY__', { backendUrl })
}