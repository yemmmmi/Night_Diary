import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

const listCustomSkills = vi.hoisted(() => vi.fn())
const createCustomSkill = vi.hoisted(() => vi.fn())
const updateCustomSkill = vi.hoisted(() => vi.fn())
const setCustomSkillEnabled = vi.hoisted(() => vi.fn())
const deleteCustomSkill = vi.hoisted(() => vi.fn())

vi.mock('@/shared/api/customSkills', () => ({
  listCustomSkills,
  createCustomSkill,
  updateCustomSkill,
  setCustomSkillEnabled,
  deleteCustomSkill,
}))

import CustomSkillsManager from '@/features/settings/CustomSkillsManager.vue'
import type { CustomSkill } from '@/shared/api/customSkills'

function skill(overrides: Partial<CustomSkill> = {}): CustomSkill {
  return {
    id: 1,
    name: '跑步复盘',
    description: '更关注配速',
    triggers: ['跑步', '配速'],
    instruction: '先问配速，再给一句鼓励。',
    enabled: true,
    version: 1,
    created_at: 0,
    updated_at: 0,
    ...overrides,
  }
}

function mountManager() {
  setActivePinia(createPinia())
  return mount(CustomSkillsManager)
}

describe('CustomSkillsManager', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    listCustomSkills.mockResolvedValue([])
    createCustomSkill.mockImplementation(async (body: Partial<CustomSkill>) => skill({ id: 2, ...body }))
    updateCustomSkill.mockImplementation(async (id: number, body: Partial<CustomSkill>) =>
      skill({ id, ...body }),
    )
    setCustomSkillEnabled.mockImplementation(async (id: number, enabled: boolean) =>
      skill({ id, enabled }),
    )
    deleteCustomSkill.mockResolvedValue(undefined)
  })

  it('loads and shows the empty hint', async () => {
    const wrapper = mountManager()
    await flushPromises()

    expect(listCustomSkills).toHaveBeenCalled()
    expect(wrapper.findAll('[data-testid="custom-skill-item"]')).toHaveLength(0)
    expect(wrapper.text()).toContain('还没有自定义技能')
  })

  it('creates a skill from the form, parsing triggers', async () => {
    const wrapper = mountManager()
    await flushPromises()

    await wrapper.find('[data-testid="custom-skill-name"]').setValue('跑步复盘')
    await wrapper.find('[data-testid="custom-skill-triggers"]').setValue('跑步, 配速')
    await wrapper.find('[data-testid="custom-skill-instruction"]').setValue('先问配速。')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(createCustomSkill).toHaveBeenCalledWith({
      name: '跑步复盘',
      description: '',
      triggers: ['跑步', '配速'],
      instruction: '先问配速。',
      enabled: true,
    })
    expect(wrapper.findAll('[data-testid="custom-skill-item"]')).toHaveLength(1)
  })

  it('renders skills and toggles enabled', async () => {
    listCustomSkills.mockResolvedValue([skill()])
    const wrapper = mountManager()
    await flushPromises()

    expect(wrapper.findAll('[data-testid="custom-skill-item"]')).toHaveLength(1)
    expect(wrapper.text()).toContain('跑步复盘')
    expect(wrapper.findAll('[data-testid="custom-skill-trigger"]')).toHaveLength(2)

    await wrapper.find('[data-testid="custom-skill-toggle"]').trigger('click')
    await flushPromises()
    expect(setCustomSkillEnabled).toHaveBeenCalledWith(1, false)
  })

  it('edits a skill and saves', async () => {
    listCustomSkills.mockResolvedValue([skill()])
    const wrapper = mountManager()
    await flushPromises()

    await wrapper.find('[data-testid="custom-skill-edit"]').trigger('click')
    expect((wrapper.find('[data-testid="custom-skill-name"]').element as HTMLInputElement).value).toBe(
      '跑步复盘',
    )

    await wrapper.find('[data-testid="custom-skill-name"]').setValue('跑步复盘 v2')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(updateCustomSkill).toHaveBeenCalledWith(
      1,
      expect.objectContaining({ name: '跑步复盘 v2' }),
    )
  })

  it('deletes a skill after confirmation', async () => {
    listCustomSkills.mockResolvedValue([skill()])
    const wrapper = mountManager()
    await flushPromises()

    await wrapper.find('[data-testid="custom-skill-delete"]').trigger('click')
    expect(wrapper.text()).toContain('删除这个技能？')

    await wrapper.find('[data-testid="custom-skill-delete-confirm"]').trigger('click')
    await flushPromises()

    expect(deleteCustomSkill).toHaveBeenCalledWith(1)
    expect(wrapper.findAll('[data-testid="custom-skill-item"]')).toHaveLength(0)
  })
})