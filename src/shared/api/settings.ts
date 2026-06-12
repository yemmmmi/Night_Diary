import { invoke } from '@tauri-apps/api/core'

export { createModel, deleteModel, getModelsStatus, listModels, testModelConnection, updateModel } from '@/shared/api/models'
export { getStats, type AppStats } from '@/shared/api/stats'

function isTauriRuntime(): boolean {
  return typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window
}

export async function listBackups(): Promise<string[]> {
  if (!isTauriRuntime()) return []
  return invoke<string[]>('list_backups')
}

export async function createBackup(): Promise<string> {
  if (!isTauriRuntime()) {
    throw new Error('备份功能仅在桌面应用中可用')
  }
  return invoke<string>('create_backup')
}

export async function restoreBackup(filename: string): Promise<void> {
  if (!isTauriRuntime()) {
    throw new Error('恢复功能仅在桌面应用中可用')
  }
  await invoke('restore_backup', { filename })
}

export async function getAppVersion(): Promise<string | null> {
  if (!isTauriRuntime()) return null
  try {
    return await invoke<string>('get_app_version')
  } catch {
    return null
  }
}
