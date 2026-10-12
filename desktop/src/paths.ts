import path from 'node:path'

export interface PathInputs {
  packaged: boolean
  resourcesPath: string
  repoRoot: string
  pythonOverride?: string
}

export interface BackendPaths {
  pythonExe: string
  serverDir: string
  frontendDir: string
}

/**
 * 打包态：运行时/服务端/前端都作为 extraResources 放在 resources/ 下。
 * 开发态：复用仓库布局与本地 venv（可用 NIGHT_DIARY_PYTHON 覆盖）。
 */
export function resolveBackendPaths(inputs: PathInputs): BackendPaths {
  if (inputs.packaged) {
    return {
      pythonExe: path.join(inputs.resourcesPath, 'runtime', 'python.exe'),
      serverDir: path.join(inputs.resourcesPath, 'server'),
      frontendDir: path.join(inputs.resourcesPath, 'frontend'),
    }
  }
  return {
    pythonExe:
      inputs.pythonOverride ??
      path.join(inputs.repoRoot, 'server', '.venv', 'Scripts', 'python.exe'),
    serverDir: path.join(inputs.repoRoot, 'server'),
    frontendDir: path.join(inputs.repoRoot, 'dist'),
  }
}