import { vi } from 'vitest'

/** Minimal axios instance mock matching getHttpClient interceptor wiring. */
export function mockAxiosClient(
  handlers: {
    get?: ReturnType<typeof vi.fn>
    post?: ReturnType<typeof vi.fn>
    put?: ReturnType<typeof vi.fn>
    patch?: ReturnType<typeof vi.fn>
    delete?: ReturnType<typeof vi.fn>
  } = {},
) {
  const interceptors = {
    request: { use: vi.fn() },
    response: { use: vi.fn() },
  }
  return {
    get: handlers.get ?? vi.fn(),
    post: handlers.post ?? vi.fn(),
    put: handlers.put ?? vi.fn(),
    patch: handlers.patch ?? vi.fn(),
    delete: handlers.delete ?? vi.fn(),
    interceptors,
  }
}
