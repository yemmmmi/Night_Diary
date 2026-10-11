import axios from 'axios'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { mockAxiosClient } from '@/__tests__/helpers/mockAxiosClient'
import { resetHttpClient } from '@/shared/api/http'
import { fetchImageObjectUrl, uploadImage } from '@/shared/api/uploads'

vi.mock('axios', () => {
  const create = vi.fn()
  return { default: { create } }
})

vi.mock('@/shared/composables/useBackend', () => ({
  resolveBackendBaseUrl: vi.fn(async () => 'http://127.0.0.1:8000'),
  waitForCoreReady: vi.fn(async () => undefined),
}))

describe('uploads API', () => {
  const get = vi.fn()
  const post = vi.fn()

  afterEach(() => {
    vi.clearAllMocks()
    resetHttpClient()
  })

  it('uploads an image as multipart form data', async () => {
    vi.mocked(axios.create).mockReturnValue(mockAxiosClient({ get, post }) as never)
    post.mockResolvedValue({
      data: {
        id: 5,
        original_filename: '海边.png',
        mime_type: 'image/png',
        size_bytes: 12,
        created_at: '2026-10-11T10:00:00',
      },
    })

    const file = new File(['fake-bytes'], '海边.png', { type: 'image/png' })
    const asset = await uploadImage(file)

    expect(post).toHaveBeenCalledTimes(1)
    const [url, body] = post.mock.calls[0]
    expect(url).toBe('/api/v1/uploads/images')
    expect(body).toBeInstanceOf(FormData)
    expect((body as FormData).get('file')).toBe(file)
    expect(asset.id).toBe(5)
  })

  it('fetches an authenticated blob and returns an object URL', async () => {
    vi.mocked(axios.create).mockReturnValue(mockAxiosClient({ get, post }) as never)
    const blob = new Blob(['bytes'], { type: 'image/png' })
    get.mockResolvedValue({ data: blob })
    const createObjectURL = vi.fn(() => 'blob:asset-5')
    Object.defineProperty(URL, 'createObjectURL', { value: createObjectURL, configurable: true })

    const url = await fetchImageObjectUrl(5)

    expect(get).toHaveBeenCalledWith('/api/v1/uploads/images/5/file', { responseType: 'blob' })
    expect(createObjectURL).toHaveBeenCalledWith(blob)
    expect(url).toBe('blob:asset-5')
  })
})