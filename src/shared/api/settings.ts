export { createModel, deleteModel, getModelsStatus, listModels, testModelConnection, updateModel } from '@/shared/api/models'
export { getStats, type AppStats } from '@/shared/api/stats'

const BACKUP_UNAVAILABLE_MESSAGE = '备份功能将在后续版本中通过 Web API 提供'

export async function listBackups(): Promise<string[]> {
  throw new Error(BACKUP_UNAVAILABLE_MESSAGE)
}

export async function createBackup(): Promise<string> {
  throw new Error(BACKUP_UNAVAILABLE_MESSAGE)
}

export async function restoreBackup(filename: string): Promise<void> {
  throw new Error(BACKUP_UNAVAILABLE_MESSAGE)
}

export async function getAppVersion(): Promise<string | null> {
  return null
}
