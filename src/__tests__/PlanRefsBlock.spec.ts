import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

const push = vi.fn()

vi.mock('vue-router', () => ({
  useRouter: () => ({ push }),
}))

import PlanRefsBlock from '@/features/plan/PlanRefsBlock.vue'
import type { SourceRef } from '@/shared/api/plan'

const refs: SourceRef[] = [
  { type: 'diary', id: 7, date: '2026-08-12', snippet: '最近三周 5 次提到失眠与换工作的犹豫' },
  { type: 'diary', id: 9, date: '2026-08-19', snippet: '又聊到了那件悬而未决的事' },
  { type: 'episodic', id: 'mem-1' },
]

function mountBlock(list: SourceRef[]) {
  return mount(PlanRefsBlock, { props: { refs: list } })
}

describe('PlanRefsBlock', () => {
  it('renders diary refs with snippet and short date link', () => {
    const wrapper = mountBlock(refs)
    expect(wrapper.text()).toContain('来自你的日记')
    expect(wrapper.text()).toContain('最近三周 5 次提到失眠')
    expect(wrapper.text()).toContain('8/12')
    expect(wrapper.text()).toContain('8/19')
  })

  it('navigates to the diary page on date click', async () => {
    const wrapper = mountBlock(refs)
    await wrapper.findAll('.plan-refs__date')[0].trigger('click')
    expect(push).toHaveBeenCalledWith('/write/7')
  })

  it('renders nothing when no diary refs', () => {
    const wrapper = mountBlock([{ type: 'episodic', id: 'mem-1' }])
    expect(wrapper.find('.plan-refs').exists()).toBe(false)
  })
})
