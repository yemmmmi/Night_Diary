import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import InkCheck from '@/shared/components/InkCheck.vue'

describe('InkCheck', () => {
  it('renders an svg check as a button', () => {
    const wrapper = mount(InkCheck, { props: { checked: false } })
    const button = wrapper.find('[data-testid="ink-check"]')
    expect(button.exists()).toBe(true)
    expect(button.element.tagName).toBe('BUTTON')
    expect(wrapper.find('svg').exists()).toBe(true)
  })

  it('toggles the done class with the checked prop', () => {
    const off = mount(InkCheck, { props: { checked: false } })
    expect(off.find('[data-testid="ink-check"]').classes()).not.toContain('ink-check--done')
    const on = mount(InkCheck, { props: { checked: true } })
    expect(on.find('[data-testid="ink-check"]').classes()).toContain('ink-check--done')
  })

  it('draws the check path only when done', () => {
    const off = mount(InkCheck, { props: { checked: false } })
    const on = mount(InkCheck, { props: { checked: true } })
    const offPath = off.find('path').attributes('stroke-dashoffset')
    const onPath = on.find('path').attributes('stroke-dashoffset')
    expect(offPath).toBe('1')
    expect(onPath).toBe('0')
  })

  it('emits toggle on click', async () => {
    const wrapper = mount(InkCheck, { props: { checked: false } })
    await wrapper.find('[data-testid="ink-check"]').trigger('click')
    expect(wrapper.emitted('toggle')).toHaveLength(1)
  })

  it('exposes an accessible label via aria', () => {
    const wrapper = mount(InkCheck, { props: { checked: false, label: '完成任务' } })
    expect(wrapper.find('[data-testid="ink-check"]').attributes('aria-label')).toBe('完成任务')
  })
})
