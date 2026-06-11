/** Map axios / fetch failures to user-facing Chinese messages. */

import { isAxiosError } from 'axios'

const HTTP_STATUS_HINTS: Record<number, string> = {
  403: '请求被拒绝（403），请检查代理或 CORS 设置',
  405: '接口方法不允许（405）：后端可能未更新，请在终端运行 make dev-api 重启后端',
  404: '资源不存在（404）',
  409: '操作冲突（409）',
  503: 'AI 引擎仍在初始化，请稍候再试',
}

export function formatApiError(err: unknown, fallback: string): string {
  if (isAxiosError(err)) {
    if (err.code === 'ERR_NETWORK' || err.message === 'Network Error') {
      return '无法连接后端，请确认 AI 引擎已启动'
    }
    const detail = err.response?.data
    if (typeof detail === 'object' && detail !== null && 'detail' in detail) {
      const message = (detail as { detail: unknown }).detail
      if (typeof message === 'string' && message.trim()) return message
    }
    const status = err.response?.status
    if (status && HTTP_STATUS_HINTS[status]) {
      return `${fallback}：${HTTP_STATUS_HINTS[status]}`
    }
    if (status) {
      return `${fallback}（HTTP ${status}）`
    }
  }

  if (err instanceof Error && err.message.trim()) {
    if (err.message === 'Network Error') {
      return '无法连接后端，请确认 AI 引擎已启动'
    }
    if (err.message.includes('status code 405')) {
      return `${fallback}：${HTTP_STATUS_HINTS[405]}`
    }
    if (err.message.includes('status code 403')) {
      return `${fallback}：${HTTP_STATUS_HINTS[403]}`
    }
    return err.message
  }

  return fallback
}
