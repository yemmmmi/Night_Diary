import { AxiosError } from 'axios'
import { describe, expect, it } from 'vitest'

import { formatApiError } from '@/shared/utils/apiError'

describe('formatApiError', () => {
  it('translates axios network errors', () => {
    const err = new AxiosError('Network Error', 'ERR_NETWORK')
    expect(formatApiError(err, '失败')).toContain('无法连接后端')
  })

  it('falls back for unknown errors', () => {
    expect(formatApiError(null, '保存日记失败')).toBe('保存日记失败')
  })
})
