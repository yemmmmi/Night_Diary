import { describe, expect, it, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { useDiaryStore } from '@/stores/diary'
import { useCardStore } from '@/stores/card'
import type { DiaryEntry } from '@/shared/api/diary'
import type { MemoryCard } from '@/shared/api/card'

const routeState = vi.hoisted(() => ({
  fullPath: '/write/7',
  params: { id: '7' } as Record<string, string>,
  query: {} as Record<string, string>,
  hash: '',
}))
const routerPush = vi.hoisted(() => vi.fn())
const routerReplace = vi.hoisted(() => vi.fn(async () => {}))

vi.mock('vue-router', () => ({
  useRoute: () => routeState,
  useRouter: () => ({ push: routerPush, replace: routerReplace }),
}))

const fetchEntry = vi.hoisted(() =>
  vi.fn(async (_id: number): Promise<DiaryEntry> => entryFixture),
)
vi.mock('@/shared/api/diary', () => ({
  getDiaryEntry: fetchEntry,
  updateDiaryEntry: vi.fn(async (_id: number, payload: { content: string }) => ({
    ...entryFixture,
    content: payload.content,
  })),
  createDiaryEntry: vi.fn(),
  deleteDiaryEntry: vi.fn(async () => {}),
  listDiaryEntries: vi.fn(async () => []),
}))

vi.mock('@/shared/api/card', () => ({
  listCards: vi.fn(async () => []),
  createCard: vi.fn(),
}))

vi.mock('@/shared/api/dev', () => ({
  getDevPipeline: vi.fn(async () => ({})),
}))

import DiaryScene from '@/pages/DiaryScene.vue'

const entryFixture: DiaryEntry = {
  id: 7,
  date: '2026-08-31',
  content: '今天去了江边，风很大。',
  created_at: '2026-08-31T21:00:00',
  updated_at: '2026-08-31T21:30:00',
} as DiaryEntry

const cardFixture = {
  card_id: 'c1',
  diary_id: 7,
  emotion: '平静',
  emotions: ['平静', '期待'],
  event_summary: '江边散步',
  mood_score: 7,
} as unknown as MemoryCard

function mountScene(cards: MemoryCard[] = []) {
  const wrapper = mount(DiaryScene, {
    global: {
      stubs: { teleport: true },
    },
  })
  const diaryStore = useDiaryStore()
  const cardStore = useCardStore()
  return { wrapper, diaryStore, cardStore, cards }
}

describe('DiaryScene（稿纸）', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    routeState.fullPath = '/write/7'
    routeState.params = { id: '7' }
    routeState.query = {}
    routeState.hash = ''
  })

  it('顶部细线栏：合上、衬线日期、保存按钮', async () => {
    const { wrapper } = mountScene()
    await flushPromises()
    expect(wrapper.find('[data-testid="diary-close"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="diary-date"]').text()).toContain('2026')
    expect(wrapper.find('[data-testid="diary-save"]').exists()).toBe(true)
  })

  it('文末尾渲染情绪印章（来自关联卡片）', async () => {
    const { wrapper, cardStore } = mountScene()
    await flushPromises()
    cardStore.cards = [cardFixture]
    await flushPromises()
    const stamps = wrapper.findAll('[data-testid="emotion-stamp"]')
    expect(stamps).toHaveLength(2)
    expect(stamps[0].text()).toBe('平静')
  })

  it('无关联卡片时不渲染印章区', async () => {
    const { wrapper } = mountScene([])
    await flushPromises()
    expect(wrapper.findAll('[data-testid="emotion-stamp"]')).toHaveLength(0)
  })

  it('底部只有导出与删除两个文字链，无任何回信元素', async () => {
    const { wrapper } = mountScene([cardFixture])
    await flushPromises()
    expect(wrapper.find('[data-testid="diary-export"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="diary-delete"]').exists()).toBe(true)
    expect(wrapper.html()).not.toContain('回信')
  })

  it('导出 Markdown 触发下载', async () => {
    const { wrapper, diaryStore } = mountScene([cardFixture])
    await flushPromises()
    diaryStore.currentEntry = { ...entryFixture }

    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(() => {})
    const createUrl = vi.fn(() => 'blob:mock')
    const revokeUrl = vi.fn()
    Object.defineProperty(URL, 'createObjectURL', { value: createUrl, configurable: true })
    Object.defineProperty(URL, 'revokeObjectURL', { value: revokeUrl, configurable: true })

    await wrapper.find('[data-testid="diary-export"]').trigger('click')
    expect(createUrl).toHaveBeenCalled()
    expect(clickSpy).toHaveBeenCalled()
    expect(revokeUrl).toHaveBeenCalledWith('blob:mock')
    clickSpy.mockRestore()
  })

  it('落纸 hero：容器带 diary-sheet--enter 类', async () => {
    const { wrapper } = mountScene()
    await flushPromises()
    expect(wrapper.find('.diary-sheet').classes()).toContain('diary-sheet--enter')
  })

  it('新建态（/write?date=...）不显示删除与导出', async () => {
    routeState.fullPath = '/write?date=2026-08-31'
    routeState.params = {}
    routeState.query = { date: '2026-08-31' }
    const { wrapper } = mountScene()
    await flushPromises()
    expect(wrapper.find('[data-testid="diary-delete"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="diary-export"]').exists()).toBe(false)
  })
})
