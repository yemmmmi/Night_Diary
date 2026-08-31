import { describe, expect, it, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

const push = vi.fn()

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {}, params: {} }),
  useRouter: () => ({ push }),
}))

const listEpisodic = vi.hoisted(() => vi.fn(async (): Promise<EpisodicEntry[]> => []))
const getProfile = vi.hoisted(() => vi.fn(async () => null))
const getOverview = vi.hoisted(() => vi.fn(async (): Promise<MemoryOverview | null> => null))
vi.mock('@/shared/api/memory', () => ({
  listEpisodic,
  getProfile,
  getOverview,
  updateEpisodic: vi.fn(async () => ({})),
  deleteEpisodic: vi.fn(async () => undefined),
}))

const getMoodTrends = vi.hoisted(() => vi.fn(async (): Promise<MoodTrendPoint[]> => []))
const listCards = vi.hoisted(() => vi.fn(async () => []))
const searchCards = vi.hoisted(() => vi.fn(async () => ({ query: '', results: [] })))
vi.mock('@/shared/api/card', () => ({
  getMoodTrends,
  listCards,
  searchCards,
  createCard: vi.fn(),
  deleteCard: vi.fn(),
  expandCardToDiary: vi.fn(),
  getCardStats: vi.fn(),
}))

const listWeekly = vi.hoisted(() => vi.fn(async (): Promise<WeeklyReport[]> => []))
vi.mock('@/shared/api/weekly', () => ({
  listWeekly,
  generateWeekly: vi.fn(),
  regenerateWeekly: vi.fn(),
}))

vi.mock('@/shared/api/plan', () => ({
  listPlans: vi.fn(async () => []),
  listTasks: vi.fn(async () => []),
  getTodayTasks: vi.fn(async () => []),
  createTask: vi.fn(async () => ({})),
  updateTaskStatus: vi.fn(async () => ({})),
}))

import MemoryScene from '@/pages/MemoryScene.vue'
import { toIsoDate, startOfWeekMonday, endOfWeekSunday, parseLocalDate } from '@/shared/utils/diaryFormat'
import type { EpisodicEntry, MemoryOverview } from '@/shared/api/memory'
import type { MoodTrendPoint } from '@/shared/api/card'
import type { WeeklyReport } from '@/shared/api/weekly'

function isoDaysAgo(days: number): string {
  const d = new Date()
  d.setDate(d.getDate() - days)
  return toIsoDate(d)
}

function mondayIso(weeksAgo = 0): string {
  return toIsoDate(startOfWeekMonday(new Date(), -weeksAgo))
}

const overview: MemoryOverview = {
  episodic_total: 12,
  episodic_from_cards: 7,
  episodic_from_diaries: 5,
  card_total: 34,
  profile_built: true,
}

function episodic(id: string): EpisodicEntry {
  return {
    entry_id: id,
    event_summary: '傍晚沿江走了三公里',
    emotion: '平静',
    reply_insight: '散步常出现在你最近的记录里。',
    importance: 0.5,
    timestamp: Math.floor(Date.now() / 1000),
    diary_ids: [],
    source: 'card',
    tags: [],
    mood_score: 0.5,
    emotions: ['平静'],
    event_date: null,
  }
}

function weeklyReport(periodStart: string, content: string): WeeklyReport {
  return {
    id: 9,
    period_start: periodStart,
    period_end: toIsoDate(endOfWeekSunday(parseLocalDate(periodStart))),
    content,
    diary_count: 3,
    card_count: 5,
    avg_mood: 0.6,
    token_cost: 800,
    execution_tier: 'medium',
    created_at: `${periodStart}T20:00:00`,
    plan_executions: [],
    week_tasks: [],
  }
}

function mountScene() {
  setActivePinia(createPinia())
  return { wrapper: mount(MemoryScene) }
}

describe('MemoryScene', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    listEpisodic.mockResolvedValue([])
    getProfile.mockResolvedValue(null)
    getOverview.mockResolvedValue(null)
    getMoodTrends.mockResolvedValue([])
    listCards.mockResolvedValue([])
    listWeekly.mockResolvedValue([])
  })

  it('renders 14 thin trend bars including zero-filled days', async () => {
    getMoodTrends.mockResolvedValue([
      { date: isoDaysAgo(0), avg_mood: 0.8, card_count: 3 },
      { date: isoDaysAgo(2), avg_mood: 0.4, card_count: 1 },
    ] as MoodTrendPoint[])

    const { wrapper } = mountScene()
    await flushPromises()

    expect(getMoodTrends).toHaveBeenCalledWith({ days: 14 })
    const bars = wrapper.findAll('[data-testid="trend-bar"]')
    expect(bars).toHaveLength(14)
    // 入场类只随进入动作挂一次（bar-grow + stagger 由 motion.css 提供）
    expect(wrapper.find('.trend-bars').classes()).toContain('trend-bars--enter')
  })

  it('scales each bar with its daily average mood', async () => {
    getMoodTrends.mockResolvedValue([
      { date: isoDaysAgo(0), avg_mood: 0.8, card_count: 3 },
      { date: isoDaysAgo(2), avg_mood: 0.4, card_count: 1 },
    ] as MoodTrendPoint[])

    const { wrapper } = mountScene()
    await flushPromises()

    const bars = wrapper.findAll('[data-testid="trend-bar"]')
    const styleOf = (i: number) => bars[i].attributes('style') ?? ''
    // 升序排列：最后一根是今天，前一根是补零日
    expect(styleOf(13)).toContain('scaleY(0.8)')
    expect(styleOf(11)).toContain('scaleY(0.4)')
    expect(styleOf(12)).toContain('scaleY(0)')
    // 悬停原生 title：日期 · 均值 x · n 张
    const title = bars[13].attributes('title') ?? ''
    expect(title).toContain(isoDaysAgo(0))
    expect(title).toContain('均值')
    expect(title).toContain('3 张')
  })

  it('renders episodic entries as thin rows without glass panels', async () => {
    listEpisodic.mockResolvedValue([episodic('e1')])
    getOverview.mockResolvedValue(overview)

    const { wrapper } = mountScene()
    await flushPromises()

    const rows = wrapper.findAll('[data-testid="episodic-row"]')
    expect(rows).toHaveLength(1)
    expect(rows[0].classes()).not.toContain('glass-panel')
    expect(wrapper.find('.glass-panel').exists()).toBe(false)
    expect(wrapper.text()).toContain('傍晚沿江走了三公里')
  })

  it('renders weekly letters from the weekly store', async () => {
    listWeekly.mockResolvedValue([
      weeklyReport(mondayIso(1), '上一周你走了很多路。' + mondayIso(1)),
      weeklyReport(mondayIso(2), '上上周你睡得不错。' + mondayIso(2)),
    ])

    const { wrapper } = mountScene()
    await flushPromises()

    expect(listWeekly).toHaveBeenCalledWith({ limit: 4 })
    const letters = wrapper.findAll('[data-testid="weekly-letter"]')
    // 本周（未生成，可发起）+ 最近两封
    expect(letters).toHaveLength(3)
    expect(wrapper.text()).toContain('上一周你走了很多路。' + mondayIso(1))
    expect(wrapper.text()).toContain('上上周你睡得不错。' + mondayIso(2))
  })

  it('keeps the four overview ledger numbers', async () => {
    getOverview.mockResolvedValue(overview)

    const { wrapper } = mountScene()
    await flushPromises()

    const stats = wrapper.findAll('[data-testid="memory-stat"]')
    expect(stats).toHaveLength(4)
    expect(stats[0].text()).toContain('12')
    expect(stats[0].text()).toContain('情节记忆')
    expect(stats[1].text()).toContain('7')
    expect(stats[2].text()).toContain('5')
    expect(stats[3].text()).toContain('34')
    expect(stats[3].text()).toContain('记忆卡片')
  })

  it('shows a quiet empty hint when no episodic entry exists', async () => {
    listEpisodic.mockResolvedValue([])

    const { wrapper } = mountScene()
    await flushPromises()

    expect(wrapper.findAll('[data-testid="episodic-row"]')).toHaveLength(0)
    expect(wrapper.find('.memory-blank').exists()).toBe(true)
    expect(wrapper.text()).toContain('还没有情节记忆')
  })
})
