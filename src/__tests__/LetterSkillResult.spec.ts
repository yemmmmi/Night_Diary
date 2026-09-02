import { describe, expect, it, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'

const { push } = vi.hoisted(() => ({ push: vi.fn() }))
vi.mock('vue-router', () => ({
  useRouter: () => ({ push }),
}))

import LetterSkillResult from '@/features/chat/LetterSkillResult.vue'
import type { SkillResult } from '@/shared/api/conversation'

function mountResult(result: SkillResult) {
  return mount(LetterSkillResult, { props: { result } })
}

describe('LetterSkillResult', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the recorded diary with date label and expandable long body', async () => {
    const longContent = '你今天六点半起床，晨跑三公里后回家冲澡。'.repeat(10)
    const wrapper = mountResult({
      skill: 'record',
      diary_id: 12,
      date: '2026-09-02',
      content: longContent,
    })
    const block = wrapper.find('[data-testid="skill-block-record"]')
    expect(block.exists()).toBe(true)
    expect(block.text()).toContain('已录入日记 · 9月2日')
    expect(wrapper.find('[data-testid="skill-record-content"]').text()).toBe(longContent)

    const toggle = wrapper.find('[data-testid="skill-record-toggle"]')
    expect(toggle.exists()).toBe(true)
    expect(toggle.text()).toBe('展开全文')
    await toggle.trigger('click')
    expect(toggle.text()).toBe('收起')
  })

  it('hides the toggle when the recorded diary is short', () => {
    const wrapper = mountResult({
      skill: 'record',
      diary_id: 13,
      date: '2026-09-02',
      content: '你今天读完了一章书。',
    })
    expect(wrapper.find('[data-testid="skill-record-toggle"]').exists()).toBe(false)
  })

  it('renders matched psychology theories as chips', () => {
    const wrapper = mountResult({
      skill: 'insight',
      matched_theories: ['情绪评价理论', '自我决定理论'],
      observations: ['情绪源于对事件的解读', '自主感是内在动机的源头'],
    })
    const block = wrapper.find('[data-testid="skill-block-insight"]')
    expect(block.exists()).toBe(true)
    expect(block.text()).toContain('洞悉 · 心理视角')
    const chips = wrapper.findAll('[data-testid="skill-insight-chip"]')
    expect(chips).toHaveLength(2)
    expect(chips[0].text()).toBe('情绪评价理论')
    expect(chips[1].text()).toBe('自我决定理论')
  })

  it('renders nothing for insight without matched theories', () => {
    const wrapper = mountResult({
      skill: 'insight',
      matched_theories: [],
      observations: [],
    })
    expect(wrapper.find('[data-testid="skill-block-insight"]').exists()).toBe(false)
  })

  it('summarizes a checkin plan and links to the plan scene', async () => {
    const wrapper = mountResult({
      skill: 'plan',
      plan_id: 'p1',
      template: 'checkin_total',
      title: '坚持减肥30天',
      target_value: 30,
      target_unit: '天',
      tasks: [],
    })
    const block = wrapper.find('[data-testid="skill-block-plan"]')
    expect(block.exists()).toBe(true)
    expect(block.text()).toContain('已创建计划')
    expect(block.text()).toContain('坚持减肥30天')
    expect(block.text()).toContain('坚持 30 天 · 每日打卡')

    await wrapper.find('[data-testid="skill-plan-open"]').trigger('click')
    expect(push).toHaveBeenCalledWith('/plan')
  })

  it('summarizes a timer plan with daily hours', () => {
    const wrapper = mountResult({
      skill: 'plan',
      plan_id: 'p2',
      template: 'timer_daily',
      title: '每日学习',
      target_value: 4,
      target_unit: '小时',
      tasks: [],
    })
    expect(wrapper.text()).toContain('每日 4 小时 · 计时推进')
  })

  it('summarizes a milestones plan with verified node counts', () => {
    const wrapper = mountResult({
      skill: 'plan',
      plan_id: 'p3',
      template: 'milestones',
      title: '学习如何剪辑',
      target_value: null,
      target_unit: null,
      tasks: [
        { id: 't1', title: '了解剪辑软件', note: '', link: 'https://example.com/1', verified: true },
        { id: 't2', title: '剪出第一支短片', note: '', link: null, verified: false },
        { id: 't3', title: '配音与字幕', note: '', link: 'https://example.com/3', verified: true },
      ],
    })
    expect(wrapper.text()).toContain('共 3 个学习节点 · 2 个附参考链接')
  })
})
