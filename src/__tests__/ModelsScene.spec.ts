import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import ModelsScene from '@/pages/ModelsScene.vue'

// mock API 层避免真实请求
vi.mock('@/shared/api/models', () => ({
  listModels: vi.fn().mockResolvedValue([]),
  getModelsStatus: vi.fn().mockResolvedValue({
    tiers: [],
    env_fallback: false,
    env_model_name: null,
  }),
  createModel: vi.fn(),
  deleteModel: vi.fn(),
  updateModel: vi.fn(),
  testModelConnection: vi.fn(),
  testStoredModelConnection: vi.fn(),
}))

// mock openExternal
vi.mock('@/shared/utils/openExternal', () => ({
  openExternal: vi.fn().mockResolvedValue(undefined),
}))

describe('ModelsScene', () => {
  it('渲染页面标题与预设卡片', async () => {
    const wrapper = mount(ModelsScene, {
      global: {
        stubs: {
          RouterLink: { template: '<a><slot /></a>' },
        },
      },
    })
    // 等待 onMounted 异步刷新
    await vi.waitFor(() => {
      expect(wrapper.text()).toContain('AI 模型')
    })
    // 预设卡片至少 8 个
    expect(wrapper.findAll('.preset-card').length).toBeGreaterThanOrEqual(8)
  })
})
