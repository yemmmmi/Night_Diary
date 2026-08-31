import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import EmotionStamp from '@/shared/components/EmotionStamp.vue'

describe('EmotionStamp', () => {
  it('renders each emotion as a stamp', () => {
    const wrapper = mount(EmotionStamp, { props: { emotions: ['平静', '期待'] } })
    const stamps = wrapper.findAll('[data-testid="emotion-stamp"]')
    expect(stamps).toHaveLength(2)
    expect(stamps[0].text()).toBe('平静')
    expect(stamps[1].text()).toBe('期待')
  })

  it('maps known emotions to their ink color class', () => {
    const wrapper = mount(EmotionStamp, { props: { emotions: ['平静'] } })
    expect(wrapper.find('[data-testid="emotion-stamp"]').classes()).toContain(
      'emotion-stamp--calm',
    )
  })

  it('falls back to the muted class for unknown emotions', () => {
    const wrapper = mount(EmotionStamp, { props: { emotions: ['虚无'] } })
    expect(wrapper.find('[data-testid="emotion-stamp"]').classes()).toContain(
      'emotion-stamp--muted',
    )
  })

  it('renders nothing for an empty list', () => {
    const wrapper = mount(EmotionStamp, { props: { emotions: [] } })
    expect(wrapper.findAll('[data-testid="emotion-stamp"]')).toHaveLength(0)
  })
})
