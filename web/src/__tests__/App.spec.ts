import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import App from '../App.vue'

describe('App', () => {
  it('renders the project title', () => {
    const wrapper = mount(App)
    expect(wrapper.text()).toContain('Night Diary V2')
  })

  it('renders the scaffold marker', () => {
    const wrapper = mount(App)
    expect(wrapper.text()).toContain('Phase 0')
  })
})
