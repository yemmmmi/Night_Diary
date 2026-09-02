import { describe, expect, it, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

vi.mock('@/shared/api/plan', () => ({
  checkinPlan: vi.fn(),
}))

import SkillPlanControls from '@/features/plan/SkillPlanControls.vue'
import { checkinPlan, type CheckinRecord, type PlanItem } from '@/shared/api/plan'

const checkinPlanMock = vi.mocked(checkinPlan)

const checkinRecord: CheckinRecord = {
  id: 'c1',
  plan_id: 'p1',
  checkin_date: '2026-09-02',
  started_at: null,
  ended_at: null,
  value: 1,
  status: 'done',
  created_at: '2026-09-02T12:00:00',
}

function templatePlan(extra: Partial<PlanItem>): PlanItem {
  return {
    id: 'p1',
    title: '坚持减肥30天',
    motivation: null,
    source_refs: [],
    status: 'active',
    source: 'agent',
    tasks: [],
    recurrence: null,
    target_value: 30,
    target_unit: '天',
    target_period: 'total',
    template: 'checkin_total',
    today_progress: { checkin_date: '2026-09-02', today_checked_in: false, total_checkins: 0 },
    ...extra,
  } as PlanItem
}

function timerPlan(extra: Partial<PlanItem>): PlanItem {
  return templatePlan({
    id: 'p2',
    title: '每日学习',
    template: 'timer_daily',
    target_value: 4,
    target_unit: '小时',
    target_period: 'daily',
    today_progress: {
      checkin_date: '2026-09-02',
      today_seconds: 0,
      target_seconds: 14400,
      running: false,
      streak_days: 0,
    },
    ...extra,
  })
}

async function mountControls(plan: PlanItem, liveSeconds?: number) {
  const wrapper = mount(SkillPlanControls, {
    props: { plan, ...(liveSeconds != null ? { liveSeconds } : {}) },
  })
  await flushPromises()
  return wrapper
}

describe('SkillPlanControls', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    checkinPlanMock.mockResolvedValue(checkinRecord)
  })

  it('checks in a checkin_total plan once and emits refresh', async () => {
    const wrapper = await mountControls(templatePlan({}))
    const btn = wrapper.find('[data-testid="checkin-btn"]')
    expect(btn.text()).toBe('打卡 +1')
    await btn.trigger('click')
    await flushPromises()
    expect(checkinPlan).toHaveBeenCalledWith('p1', 'checkin')
    expect(wrapper.emitted('refresh')).toHaveLength(1)
  })

  it('disables the checkin button after a same-day check-in', async () => {
    const wrapper = await mountControls(
      templatePlan({ today_progress: { checkin_date: '2026-09-02', today_checked_in: true, total_checkins: 1 } }),
    )
    const btn = wrapper.find('[data-testid="checkin-btn"]')
    expect(btn.attributes('disabled')).toBeDefined()
    expect(btn.text()).toBe('今日已打卡')
    await btn.trigger('click')
    expect(checkinPlan).not.toHaveBeenCalled()
  })

  it('marks the plan as completed for finished plans', async () => {
    const wrapper = await mountControls(templatePlan({ status: 'completed' }))
    const btn = wrapper.find('[data-testid="checkin-btn"]')
    expect(btn.attributes('disabled')).toBeDefined()
    expect(btn.text()).toBe('计划已完成')
  })

  it('starts the timer of a timer_daily plan and shows the running clock', async () => {
    const wrapper = await mountControls(timerPlan({}))
    const btn = wrapper.find('[data-testid="timer-btn"]')
    expect(btn.text()).toContain('开始计时')
    await btn.trigger('click')
    await flushPromises()
    expect(checkinPlan).toHaveBeenCalledWith('p2', 'start')
    expect(wrapper.emitted('refresh')).toHaveLength(1)
  })

  it('stops a running timer and prefers live seconds on the clock', async () => {
    const wrapper = await mountControls(
      timerPlan({
        today_progress: {
          checkin_date: '2026-09-02',
          today_seconds: 3600,
          target_seconds: 14400,
          running: true,
          started_at: '2026-09-02T12:00:00',
          streak_days: 3,
        },
      }),
      5400,
    )
    const btn = wrapper.find('[data-testid="timer-btn"]')
    expect(btn.text()).toContain('停止计时')
    expect(wrapper.find('[data-testid="timer-elapsed"]').text()).toContain('1小时30分')
    await btn.trigger('click')
    await flushPromises()
    expect(checkinPlan).toHaveBeenCalledWith('p2', 'stop')
  })

  it('shows the streak line when the timer is idle with history', async () => {
    const wrapper = await mountControls(
      timerPlan({
        today_progress: {
          checkin_date: '2026-09-02',
          today_seconds: 0,
          target_seconds: 14400,
          running: false,
          streak_days: 5,
        },
      }),
    )
    expect(wrapper.text()).toContain('已坚持 5 天')
    expect(wrapper.find('[data-testid="timer-elapsed"]').exists()).toBe(false)
  })

  it('shows the completion dialog when the daily target is reached without stopping the timer', async () => {
    const wrapper = await mountControls(
      timerPlan({
        today_progress: {
          checkin_date: '2026-09-02',
          today_seconds: 14400,
          target_seconds: 14400,
          running: true,
          streak_days: 1,
        },
      }),
    )
    const dialog = wrapper.find('[data-testid="timer-complete-dialog"]')
    expect(dialog.exists()).toBe(true)
    expect(dialog.text()).toContain('「每日学习」今日已达标')
    // 计时不自动停止：按钮仍为停止态
    expect(wrapper.find('[data-testid="timer-btn"]').text()).toContain('停止计时')
    expect(wrapper.find('[data-testid="timer-elapsed"]').text()).toContain('今日已达标')
    await dialog.find('button').trigger('click')
    expect(wrapper.find('[data-testid="timer-complete-dialog"]').exists()).toBe(false)
  })

  it('shows an inline error when a check-in request fails', async () => {
    checkinPlanMock.mockRejectedValueOnce(new Error('network'))
    const wrapper = await mountControls(templatePlan({}))
    await wrapper.find('[data-testid="checkin-btn"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('.skill-ctrl__error').text()).toBe('打卡失败，稍后再试')
    expect(wrapper.emitted('refresh')).toBeUndefined()
  })

  it('renders nothing for legacy plans without a template', async () => {
    const wrapper = await mountControls(templatePlan({ template: null }))
    expect(wrapper.find('[data-testid="checkin-btn"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="timer-btn"]').exists()).toBe(false)
  })
})
