import { AxiosError } from 'axios'
import { describe, expect, it } from 'vitest'

import { formatApiError } from '@/shared/utils/apiError'

describe('formatApiError', () => {
  it('translates axios network errors', () => {
    const err = new AxiosError('Network Error', 'ERR_NETWORK')
    expect(formatApiError(err, '失败')).toContain('无法连接后端')
  })

  it('maps HTTP 405 to actionable hint', () => {
    const err = new AxiosError('Request failed', undefined, undefined, undefined, {
      status: 405,
      data: {},
      statusText: 'Method Not Allowed',
      headers: {},
      config: {} as never,
    })
    expect(formatApiError(err, '删除失败')).toContain('405')
    expect(formatApiError(err, '删除失败')).toContain('make dev-api')
  })

  it('maps HTTP 403 to rejection hint', () => {
    const err = new AxiosError('Forbidden', undefined, undefined, undefined, {
      status: 403,
      data: {},
      statusText: 'Forbidden',
      headers: {},
      config: {} as never,
    })
    expect(formatApiError(err, '操作失败')).toContain('403')
  })

  it('prefers backend detail over status hint', () => {
    const err = new AxiosError('Bad Request', undefined, undefined, undefined, {
      status: 422,
      data: { detail: 'API Key 无效（401）' },
      statusText: 'Unprocessable Entity',
      headers: {},
      config: {} as never,
    })
    expect(formatApiError(err, '保存失败')).toBe('API Key 无效（401）')
  })

  it('falls back for unknown errors', () => {
    expect(formatApiError(null, '保存日记失败')).toBe('保存日记失败')
  })
})
