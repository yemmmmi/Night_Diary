import path from 'node:path'

import { app, BrowserWindow } from 'electron'

import { BackendProcess } from './backend'
import { resolveBackendPaths } from './paths'
import { findFreePort } from './port'

const backend = new BackendProcess(
  resolveBackendPaths({
    packaged: app.isPackaged,
    resourcesPath: process.resourcesPath,
    repoRoot: path.resolve(__dirname, '..', '..'),
    pythonOverride: process.env.NIGHT_DIARY_PYTHON,
  }),
)

let mainWindow: BrowserWindow | null = null

async function boot(): Promise<void> {
  const port = await findFreePort()
  const dataDir = path.join(app.getPath('appData'), 'night-diary')

  const { child, url } = backend.start({ port, dataDir })
  child.stderr?.on('data', (chunk) => console.error('[backend]', String(chunk)))
  child.on('exit', (code) => {
    if (code !== 0 && code !== null) {
      console.error(`[backend] exited unexpectedly with code ${code}`)
    }
  })

  await backend.waitReady(url)

  mainWindow = new BrowserWindow({
    width: 1100,
    height: 760,
    minWidth: 900,
    minHeight: 600,
    backgroundColor: '#FAF7F3',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      additionalArguments: [`--backend-url=${url}`],
    },
  })
  await mainWindow.loadURL(url)
}

app.whenReady().then(boot).catch((error) => {
  console.error('[desktop] boot failed:', error)
  app.quit()
})

app.on('window-all-closed', () => {
  backend.stop()
  app.quit()
})

app.on('before-quit', () => {
  backend.stop()
})