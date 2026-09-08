import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'

import ChatInput from '@/features/chat/ChatInput.vue'
import type { SkillSpec } from '@/shared/api/conversation'

const SKILLS: SkillSpec[] = [
  { id: 'record', label: '记录', description: '把这封信转写成一篇日记' },
  { id: 'insight', label: '洞悉', description: '以心理视角分析这封信' },
  { id: 'plan', label: '计划', description: '把这封信整理成一个计划' },
]

function mountInput(skills: SkillSpec[] = SKILLS) {
  return mount(ChatInput, {
    props: { skills },
  })
}

async function typeValue(wrapper: ReturnType<typeof mountInput>, value: string) {
  await wrapper.find('[data-testid="letter-input"] textarea').setValue(value)
  await nextTick()
}

async function pressKey(
  wrapper: ReturnType<typeof mountInput>,
  key: string,
  shiftKey = false,
) {
  await wrapper
    .find('[data-testid="letter-input"] textarea')
    .trigger('keydown', { key, shiftKey })
  await nextTick()
}

function fieldValue(wrapper: ReturnType<typeof mountInput>) {
  return (wrapper.find('[data-testid="letter-input"] textarea').element as HTMLTextAreaElement)
    .value
}

describe('ChatInput skills', () => {
  it('renders auto plus one chip per discovered skill', () => {
    const wrapper = mountInput()
    const chips = wrapper.findAll('[data-testid^="skill-chip-"]')
    expect(chips.map((chip) => chip.text())).toEqual(['自动', '记录', '洞悉', '计划'])
    expect(wrapper.find('[data-testid="skill-chip-auto"]').classes()).toContain('is-active')
    expect(wrapper.find('[data-testid="skill-chip-record"]').attributes('title')).toBe(
      '把这封信转写成一篇日记',
    )
  })

  it('marks the chip matching the selected skill as active', async () => {
    const wrapper = mountInput()
    await wrapper.setProps({ skill: 'insight' })
    expect(wrapper.find('[data-testid="skill-chip-insight"]').classes()).toContain('is-active')
    expect(wrapper.find('[data-testid="skill-chip-auto"]').classes()).not.toContain('is-active')
  })

  it('emits update:skill when a chip is clicked', async () => {
    const wrapper = mountInput()
    await wrapper.find('[data-testid="skill-chip-plan"]').trigger('click')
    expect(wrapper.emitted('update:skill')?.[0]).toEqual(['plan'])
  })
})

describe('ChatInput slash command menu', () => {
  it('opens the menu when the text starts with /', async () => {
    const wrapper = mountInput()
    expect(wrapper.find('[data-testid="skill-menu"]').exists()).toBe(false)

    await typeValue(wrapper, '/')
    const menu = wrapper.find('[data-testid="skill-menu"]')
    expect(menu.exists()).toBe(true)
    expect(wrapper.findAll('[data-testid^="skill-menu-item-"]')).toHaveLength(3)
    expect(menu.text()).toContain('把这封信转写成一篇日记')
  })

  it('filters items by the query after /', async () => {
    const wrapper = mountInput()
    await typeValue(wrapper, '/洞悉')
    const items = wrapper.findAll('[data-testid^="skill-menu-item-"]')
    expect(items).toHaveLength(1)
    expect(items[0].attributes('data-testid')).toBe('skill-menu-item-insight')
  })

  it('shows an empty hint when nothing matches', async () => {
    const wrapper = mountInput()
    await typeValue(wrapper, '/不存在的技能')
    expect(wrapper.findAll('[data-testid^="skill-menu-item-"]')).toHaveLength(0)
    expect(wrapper.find('[data-testid="skill-menu"]').text()).toContain('没有匹配的技能')
  })

  it('selects via keyboard: ArrowDown then Enter emits the skill and strips the command token', async () => {
    const wrapper = mountInput()
    await typeValue(wrapper, '/')

    await pressKey(wrapper, 'ArrowDown')
    const items = wrapper.findAll('[data-testid^="skill-menu-item-"]')
    expect(items).toHaveLength(3)
    expect(items[0].classes()).not.toContain('is-active')
    expect(items[1].classes()).toContain('is-active')

    await pressKey(wrapper, 'Enter')
    expect(wrapper.emitted('update:skill')?.[0]).toEqual(['insight'])
    expect(fieldValue(wrapper)).toBe('')
    expect(wrapper.find('[data-testid="skill-menu"]').exists()).toBe(false)
  })

  it('keeps the remainder of the text when selecting a skill with Tab', async () => {
    const wrapper = mountInput()
    await typeValue(wrapper, '/记录 整理了房间，读了几页书')
    await pressKey(wrapper, 'Tab')
    expect(wrapper.emitted('update:skill')?.[0]).toEqual(['record'])
    expect(fieldValue(wrapper)).toBe('整理了房间，读了几页书')
  })

  it('closes the menu on Escape by dropping the command token', async () => {
    const wrapper = mountInput()
    await typeValue(wrapper, '/记')
    await pressKey(wrapper, 'Escape')
    expect(wrapper.find('[data-testid="skill-menu"]').exists()).toBe(false)
    expect(fieldValue(wrapper)).toBe('')
    expect(wrapper.emitted('update:skill')).toBeUndefined()
  })

  it('selects a skill by mouse click', async () => {
    const wrapper = mountInput()
    await typeValue(wrapper, '/')
    await wrapper.find('[data-testid="skill-menu-item-plan"]').trigger('click')
    expect(wrapper.emitted('update:skill')?.[0]).toEqual(['plan'])
    expect(fieldValue(wrapper)).toBe('')
    expect(wrapper.find('[data-testid="skill-menu"]').exists()).toBe(false)
  })

  it('sends normally with Enter when no slash command is active', async () => {
    const wrapper = mountInput()
    await typeValue(wrapper, '今天有点累')
    await pressKey(wrapper, 'Enter')
    expect(wrapper.emitted('send')?.[0]).toEqual(['今天有点累'])
  })

  it('sends the raw text with Enter when the menu has no matches', async () => {
    const wrapper = mountInput()
    await typeValue(wrapper, '/斜杠开头的普通句子')
    await pressKey(wrapper, 'Enter')
    expect(wrapper.emitted('send')?.[0]).toEqual(['/斜杠开头的普通句子'])
  })
})
