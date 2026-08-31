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

  it('redirects /review to the memory scene', async () => {
    const router = buildRouter()
    await router.push('/review')
    expect(router.currentRoute.value.name).toBe('memory')
  })

  it('redirects /weekly to the timeline week view', async () => {
    const router = buildRouter()
    await router.push('/weekly')
    expect(router.currentRoute.value.path).toBe('/timeline')
    expect(router.currentRoute.value.query.view).toBe('week')
  })
})

describe('home is the Today scene', () => {
  it('mounts TodayScene at / and TimelineScene at /timeline', async () => {
    const router = buildRouter()
    await router.push('/')
    expect(router.currentRoute.value.name).toBe('home')
    await router.push('/timeline')
    expect(router.currentRoute.value.name).toBe('timeline')
  })
})
