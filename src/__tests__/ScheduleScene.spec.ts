import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('vue-router', () => ({
  useRoute: () => ({ name: 'schedules' }),
  useRouter: () => ({ push: vi.fn() }),
}))

const listKinds = vi.hoisted(() => vi.fn())
const listSchedules = vi.hoisted(() => vi.fn())
const createSchedule = vi.hoisted(() => vi.fn())
const updateSchedule = vi.hoisted(() => vi.fn())
const deleteSchedule = vi.hoisted(() => vi.fn())
const triggerSchedule = vi.hoisted(() => vi.fn())
const listRuns = vi.hoisted(() => vi.fn())

vi.mock('@/shared/api/schedule', () => ({
  listKinds,
  listSchedules,
  createSchedule,
  updateSchedule,
  deleteSchedule,
  triggerSchedule,
  listRuns,
}))

import ScheduleScene from '@/pages/ScheduleScene.vue'
import type { ScheduledTask, ScheduledTaskRun } from '@/shared/api/schedule'

const kinds = [
  { kind: 'daily_review', label: '每日回顾', default_mode: 'script', allowed_modes: ['agent', 'script'] },
  { kind: 'weekly_insight', label: '每周洞察', default_mode: 'agent', allowed_modes: ['agent'] },
  { kind: 'plan_reminder', label: '计划提醒', default_mode: 'script', allowed_modes: ['script'] },
]

function task(overrides: Partial<ScheduledTask> = {}): ScheduledTask {
  return {
    id: 't1',
    kind: 'daily_review',
    kind_label: '每日回顾',
    mode: 'script',
    mode_label: '纯数据（零 LLM）',
    sink: 'inbox',
    cron_expr: '0 22 * * *',
    payload: {},
    enabled: true,
    next_run_at: '2026-10-12T22:00:00',
    last_run_at: null,
    last_status: null,
    created_at: '2026-10-11T10:00:00',
    ...overrides,
  }
}

function run(): ScheduledTaskRun {
  return {
    id: 1,
    task_id: 't1',
    kind: 'daily_review',
    status: 'done',
    summary: '今天有 2 条记录。',
    error: null,
    started_at: '2026-10-11T22:00:00',
    finished_at: '2026-10-11T22:00:05',
  }
}

function mountScene() {
  setActivePinia(createPinia())
  return mount(ScheduleScene, {
    global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
  })
}

describe('ScheduleScene', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    listKinds.mockResolvedValue(kinds)
    listSchedules.mockResolvedValue([])
    createSchedule.mockImplementation(
      async (body: { kind: string; cron_expr: string; enabled?: boolean; mode?: string }) =>
        task({
          id: 'new',
          kind: body.kind,
          cron_expr: body.cron_expr,
          enabled: body.enabled ?? true,
          mode: body.mode ?? 'script',
        }),
    )
    updateSchedule.mockImplementation(
      async (id: string, patch: Partial<ScheduledTask>) => task({ id, ...patch }),
    )
    deleteSchedule.mockResolvedValue(undefined)
    triggerSchedule.mockResolvedValue(task())
    listRuns.mockResolvedValue([])
  })

  it('loads kinds and shows the empty hint', async () => {
    const wrapper = mountScene()
    await flushPromises()

    expect(listKinds).toHaveBeenCalled()
    expect(wrapper.findAll('[data-testid="schedule-item"]')).toHaveLength(0)
    expect(wrapper.text()).toContain('还没有定时任务')
    const select = wrapper.find('[data-testid="schedule-kind"]').element as HTMLSelectElement
    expect(select.value).toBe('daily_review')
  })

  it('creates a task from the form', async () => {
    const wrapper = mountScene()
    await flushPromises()

    await wrapper.find('[data-testid="schedule-kind"]').setValue('plan_reminder')
    await wrapper.find('[data-testid="schedule-cron"]').setValue('0 9 * * *')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(createSchedule).toHaveBeenCalledWith({
      kind: 'plan_reminder',
      cron_expr: '0 9 * * *',
      enabled: true,
    })
    expect(wrapper.findAll('[data-testid="schedule-item"]')).toHaveLength(1)
  })

  it('offers an execution mode only for kinds that support more than one', async () => {
    const wrapper = mountScene()
    await flushPromises()

    // daily_review is the default selection and supports script + agent.
    const modeSelect = wrapper.find('[data-testid="schedule-mode"]')
    expect(modeSelect.exists()).toBe(true)
    expect((modeSelect.element as HTMLSelectElement).value).toBe('script')

    await wrapper.find('[data-testid="schedule-kind"]').setValue('plan_reminder')
    await flushPromises()
    expect(wrapper.find('[data-testid="schedule-mode"]').exists()).toBe(false)
  })

  it('sends the chosen mode when creating', async () => {
    const wrapper = mountScene()
    await flushPromises()

    await wrapper.find('[data-testid="schedule-mode"]').setValue('agent')
    await wrapper.find('[data-testid="schedule-cron"]').setValue('0 22 * * *')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(createSchedule).toHaveBeenCalledWith({
      kind: 'daily_review',
      cron_expr: '0 22 * * *',
      enabled: true,
      mode: 'agent',
    })
  })

  it('shows the execution mode on a task', async () => {
    listSchedules.mockResolvedValue([task({ mode: 'agent', mode_label: '生成型（走 LLM）' })])
    const wrapper = mountScene()
    await flushPromises()

    expect(wrapper.find('[data-testid="schedule-mode-badge"]').text()).toContain('生成型')
  })

  it('renders tasks and toggles enabled', async () => {
    listSchedules.mockResolvedValue([task()])
    const wrapper = mountScene()
    await flushPromises()

    expect(wrapper.findAll('[data-testid="schedule-item"]')).toHaveLength(1)
    expect(wrapper.text()).toContain('每日回顾')
    expect(wrapper.text()).toContain('0 22 * * *')

    await wrapper.find('[data-testid="schedule-toggle"]').trigger('click')
    await flushPromises()
    expect(updateSchedule).toHaveBeenCalledWith('t1', { enabled: false })
  })

  it('triggers a task immediately', async () => {
    listSchedules.mockResolvedValue([task()])
    const wrapper = mountScene()
    await flushPromises()

    await wrapper.find('[data-testid="schedule-trigger"]').trigger('click')
    await flushPromises()
    expect(triggerSchedule).toHaveBeenCalledWith('t1')
  })

  it('edits the cron expression inline', async () => {
    listSchedules.mockResolvedValue([task()])
    const wrapper = mountScene()
    await flushPromises()

    await wrapper.find('[data-testid="schedule-edit"]').trigger('click')
    await wrapper.find('[data-testid="schedule-edit-cron"]').setValue('30 8 * * *')
    await wrapper.find('[data-testid="schedule-save-edit"]').trigger('click')
    await flushPromises()

    expect(updateSchedule).toHaveBeenCalledWith('t1', { cron_expr: '30 8 * * *' })
  })

  it('deletes a task after confirmation', async () => {
    listSchedules.mockResolvedValue([task()])
    const wrapper = mountScene()
    await flushPromises()

    await wrapper.find('[data-testid="schedule-delete"]').trigger('click')
    expect(wrapper.find('[data-testid="schedule-delete-confirm"]').exists()).toBe(true)

    await wrapper.find('[data-testid="schedule-delete-confirm"]').trigger('click')
    await flushPromises()

    expect(deleteSchedule).toHaveBeenCalledWith('t1')
    expect(wrapper.findAll('[data-testid="schedule-item"]')).toHaveLength(0)
  })

  it('shows execution receipts when expanded', async () => {
    listSchedules.mockResolvedValue([task()])
    listRuns.mockResolvedValue([run()])
    const wrapper = mountScene()
    await flushPromises()

    await wrapper.find('[data-testid="schedule-runs-toggle"]').trigger('click')
    await flushPromises()

    expect(listRuns).toHaveBeenCalledWith('t1', 20)
    const runs = wrapper.findAll('[data-testid="schedule-run"]')
    expect(runs).toHaveLength(1)
    expect(runs[0].text()).toContain('今天有 2 条记录。')
  })
})