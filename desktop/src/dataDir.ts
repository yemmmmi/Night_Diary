import fs from 'node:fs'
import path from 'node:path'

export interface DataDirInputs {
  packaged: boolean
  /** process.resourcesPath（打包态为 <install>/resources）。 */
  resourcesPath: string
  /** app.getPath('appData')（开发态落 %APPDATA%）。 */
  appData: string
  /** 安装目录名，同时也是旧的 AppData 子目录名。 */
  dirName?: string
  /** 便于测试：覆盖「目录是否存在」判断。 */
  existsSync?: (p: string) => boolean
  /** 便于测试：覆盖「目录内容列表」判断。 */
  readdirSync?: (p: string) => string[]
  /** 便于测试：执行迁移时的回调。 */
  migrate?: (from: string, to: string) => void
}

const DEFAULT_DIR_NAME = 'night-diary'

/**
 * 决定后端数据目录。
 *
 * - 打包态：便携模式，数据放在安装根目录下的 `data/`（与程序同盘，
 *   例如 `D:\NightDiary\data`）。安装根 = resourcesPath 的上一级。
 * - 开发态：沿用 `%APPDATA%\night-diary`，与 Docker/本地脚本一致。
 *
 * 首次使用便携目录时，若旧的 AppData 目录存在且非空，会迁移过去，
 * 保证已安装用户升级后不丢日记。
 */
export function resolveDataDir(inputs: DataDirInputs): string {
  const dirName = inputs.dirName ?? DEFAULT_DIR_NAME

  if (!inputs.packaged) {
    return path.join(inputs.appData, dirName)
  }

  const installRoot = path.dirname(inputs.resourcesPath)
  const portableDir = path.join(installRoot, 'data')
  const legacyDir = path.join(inputs.appData, dirName)
  const exists = inputs.existsSync ?? fs.existsSync

  if (!exists(portableDir) && exists(legacyDir) && !isEmptyDir(legacyDir, exists, inputs.readdirSync)) {
    const migrate = inputs.migrate ?? defaultMigrate
    migrate(legacyDir, portableDir)
  }

  return portableDir
}

function isEmptyDir(
  dir: string,
  exists: (p: string) => boolean,
  readdir?: (p: string) => string[],
): boolean {
  if (!exists(dir)) return true
  try {
    return (readdir ? readdir(dir) : fs.readdirSync(dir)).length === 0
  } catch {
    return true
  }
}

/**
 * 递归迁移旧数据目录。失败不阻断启动——后端会在新目录重新初始化，
 * 旧数据仍保留在原处以便用户手动恢复。
 */
function defaultMigrate(from: string, to: string): void {
  try {
    fs.mkdirSync(path.dirname(to), { recursive: true })
    fs.cpSync(from, to, { recursive: true })
  } catch {
    // 迁移失败时保持静默：新数据目录不存在，后端首次启动会自建。
  }
}
