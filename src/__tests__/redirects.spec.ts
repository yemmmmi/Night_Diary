import { describe, expect, it } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import { appRoutes } from '@/router'

function buildRouter() {
  return createRouter({ history: createMemoryHistory(), routes: appRoutes })
}

describe('legacy route redirects', () => {
  it('redirects /review/:diaryId to the write page', async () => {
    const router = buildRouter()
    await router.push('/review/123')
    expect(router.currentRoute.value.name).toBe('write-edit')
    expect(router.currentRoute.value.params.id).toBe('123')
  })
})
