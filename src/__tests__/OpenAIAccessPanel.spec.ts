import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const resolveBackendBaseUrl = vi.hoisted(() => vi.fn())

vi.mock('@/shared/composables/useBackend', () => ({
  resolveBackendBaseUrl,
}))

import OpenAIAccessPanel from '@/features/settings/OpenAIAccessPanel.vue'

describe('OpenAIAccessPanel', () => {
  const writeText = vi.fn().mockResolvedValue(undefined)

  beforeEach(() => {
    vi.clearAllMocks()
    resolveBackendBaseUrl.mockResolvedValue('http://127.0.0.1:8000')
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText },
      configurable: true,
    })
  })

  it('shows the OpenAI-compatible endpoints built from the backend base url', async () => {
    const wrapper = mount(OpenAIAccessPanel)
    await flushPromises()

    expect(wrapper.find('[data-testid="openai-chat-endpoint"]').text()).toBe(
      'http://127.0.0.1:8000/v1/chat/completions',
    )
    expect(wrapper.find('[data-testid="openai-models-endpoint"]').text()).toBe(
      'http://127.0.0.1:8000/v1/models',
    )
    expect(wrapper.text()).toContain('Authorization: Bearer')
  })

  it('normalizes a trailing slash in the base url', async () => {
    resolveBackendBaseUrl.mockResolvedValue('http://127.0.0.1:8000/')
    const wrapper = mount(OpenAIAccessPanel)
    await flushPromises()

    expect(wrapper.find('[data-testid="openai-chat-endpoint"]').text()).toBe(
      'http://127.0.0.1:8000/v1/chat/completions',
    )
  })

  it('copies the chat endpoint to the clipboard', async () => {
    const wrapper = mount(OpenAIAccessPanel)
    await flushPromises()

    await wrapper.find('[data-testid="openai-copy-chat"]').trigger('click')
    await flushPromises()

    expect(writeText).toHaveBeenCalledWith('http://127.0.0.1:8000/v1/chat/completions')
    expect(wrapper.find('[data-testid="openai-copy-chat"]').text()).toBe('已复制')
  })
})