/** Map axios / fetch failures to user-facing Chinese messages. */

import { isAxiosError } from 'axios'

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
    if (err.response?.status) {
      return `${fallback}（HTTP ${err.response.status}）`
    }
  }

  if (err instanceof Error && err.message.trim()) {
    if (err.message === 'Network Error') {
      return '无法连接后端，请确认 AI 引擎已启动'
    }
    return err.message
  }

  return fallback
}
