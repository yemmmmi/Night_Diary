import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import InkGrinding from '@/shared/components/InkGrinding.vue'

describe('InkGrinding', () => {
  it('renders as a live status region', () => {
    const wrapper = mount(InkGrinding)
    const root = wrapper.find('[data-testid="ink-grinding"]')
    expect(root.exists()).toBe(true)
    expect(root.attributes('role')).toBe('status')
    expect(root.attributes('aria-label')).toBe('研墨中')
  })

  it('renders the ink dot and the spreading halo', () => {
    const wrapper = mount(InkGrinding)
    expect(wrapper.find('.ink-grinding__dot').exists()).toBe(true)
    expect(wrapper.find('.ink-grinding__halo').exists()).toBe(true)
  })

  it('defaults to the compact size', () => {
    const wrapper = mount(InkGrinding)
    expect(wrapper.find('[data-testid="ink-grinding"]').classes()).toContain('ink-grinding--sm')
  })
})
