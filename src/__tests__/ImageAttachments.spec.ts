import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const uploadImage = vi.hoisted(() =>
  vi.fn(async (file: File) => ({
    id: 42,
    original_filename: file.name,
    mime_type: file.type,
    size_bytes: file.size,
    created_at: '2026-10-11T10:00:00',
  })),
)
const fetchImageObjectUrl = vi.hoisted(() => vi.fn(async (id: number) => `blob:${id}`))

vi.mock('@/shared/api/uploads', () => ({
  ACCEPTED_IMAGE_TYPES: 'image/jpeg,image/png,image/webp',
  MAX_IMAGE_BYTES: 10 * 1024 * 1024,
  uploadImage,
  fetchImageObjectUrl,
}))

import ImageAttachments from '@/features/diary/ImageAttachments.vue'

function selectFiles(wrapper: ReturnType<typeof mount>, files: File[]) {
  const input = wrapper.find('input[type="file"]')
  Object.defineProperty(input.element, 'files', { value: files, configurable: true })
  return input.trigger('change')
}

describe('ImageAttachments', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    Object.defineProperty(URL, 'revokeObjectURL', { value: vi.fn(), configurable: true })
  })

  it('renders a thumbnail for each attached asset', async () => {
    const wrapper = mount(ImageAttachments, { props: { modelValue: [7] } })
    await flushPromises()
    expect(wrapper.findAll('[data-testid="image-attachment"]')).toHaveLength(1)
    expect(fetchImageObjectUrl).toHaveBeenCalledWith(7)
    expect(wrapper.find('img').attributes('src')).toBe('blob:7')
  })

  it('uploads a picked file and emits the new asset id', async () => {
    const wrapper = mount(ImageAttachments, { props: { modelValue: [] } })
    const file = new File(['bytes'], '海边.png', { type: 'image/png' })

    await selectFiles(wrapper, [file])
    await flushPromises()

    expect(uploadImage).toHaveBeenCalledWith(file)
    const emitted = wrapper.emitted('update:modelValue')
    expect(emitted?.[0]).toEqual([[42]])
  })

  it('removes an attachment and emits the filtered list', async () => {
    const wrapper = mount(ImageAttachments, { props: { modelValue: [7, 8] } })
    await flushPromises()

    await wrapper.findAll('[data-testid="image-remove"]')[0].trigger('click')

    const emitted = wrapper.emitted('update:modelValue')
    expect(emitted?.[0]).toEqual([[8]])
  })

  it('rejects an oversized file without uploading', async () => {
    const wrapper = mount(ImageAttachments, { props: { modelValue: [] } })
    const big = new File(['x'], 'big.png', { type: 'image/png' })
    Object.defineProperty(big, 'size', { value: 11 * 1024 * 1024 })

    await selectFiles(wrapper, [big])
    await flushPromises()

    expect(uploadImage).not.toHaveBeenCalled()
    expect(wrapper.find('[data-testid="image-error"]').exists()).toBe(true)
  })

  it('hides add and remove controls in readonly mode', async () => {
    const wrapper = mount(ImageAttachments, { props: { modelValue: [7], readonly: true } })
    await flushPromises()
    expect(wrapper.find('[data-testid="image-add"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="image-remove"]').exists()).toBe(false)
  })
})