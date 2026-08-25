import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

const push = vi.fn()

vi.mock('vue-router', () => ({
  useRouter: () => ({ push }),
}))

vi.mock('@/shared/api/diary', () => ({
  listDiaryEntries: vi.fn(async () => []),
}))
vi.mock('@/shared/api/analysis', () => ({
  getAnalysis: vi.fn(async () => {
    throw Object.assign(new Error('404'), { response: { status: 404 } })
  }),
}))
vi.mock('@/shared/api/card', () => ({
  listCards: vi.fn(async () => []),
}))
vi.mock('@/shared/utils/cardFormat', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/shared/utils/cardFormat')>()),
  findCardForDiary: vi.fn(() => null),
}))

import DetailPanel from '@/features/timeline/DetailPanel.vue'
import { useTimelineStore } from '@/stores/timeline'
import { useDiaryStore } from '@/stores/diary'
import type { DiaryEntry } from '@/shared/api/diary'

const entry: DiaryEntry = {
  id: 7,
  content: '今天走了很久，想通了一些事。',
  date: '2026-08-25',
  weather: '晴',
  reply: '听起来散步帮你理清了思绪。',
  created_at: '2026-08-25T21:00:00',
  updated_at: '2026-08-25T21:30:00',
}

function mountPanel() {
  setActivePinia(createPinia())
  const timeline = useTimelineStore()
  const diaryStore = useDiaryStore()
  diaryStore.removeEntry = vi.fn(async () => {})
  timeline.entries = [entry]
  timeline.selectEntry(7)
  return { wrapper: mount(DetailPanel), timeline, diaryStore }
}

function findButton(wrapper: ReturnType<typeof mount>, text: string) {
  const button = wrapper.findAll('button').find((b) => b.text().includes(text))
  expect(button, `button containing "${text}" should exist`).toBeTruthy()
  return button!
}

describe('DetailPanel', () => {
  it('renders date, weather, summary, status and reply preview', () => {
    const { wrapper } = mountPanel()
    expect(wrapper.text()).toContain('2026-08-25')
    expect(wrapper.text()).toContain('晴')
    expect(wrapper.text()).toContain('今天走了很久')
    expect(wrapper.text()).toContain('听起来散步帮你理清了思绪')
  })

  it('navigates to write page on continue', async () => {
    const { wrapper } = mountPanel()
    await findButton(wrapper, '继续编辑').trigger('click')
    expect(push).toHaveBeenCalledWith('/write/7')
  })

  it('navigates to analysis page on view reply', async () => {
    const { wrapper } = mountPanel()
    await findButton(wrapper, '查看回信').trigger('click')
    expect(push).toHaveBeenCalledWith('/analysis/7')
  })

  it('deletes entry after confirmation and clears selection', async () => {
    const { wrapper, timeline, diaryStore } = mountPanel()
    await findButton(wrapper, '删除日记').trigger('click')
    await findButton(wrapper, '确认删除').trigger('click')
    expect(diaryStore.removeEntry).toHaveBeenCalledWith(7)
    expect(timeline.selectedEntry).toBeNull()
  })

  it('hides reply block for drafts', () => {
    const draft = { ...entry, content: '走了很久', reply: null }
    setActivePinia(createPinia())
    const timeline = useTimelineStore()
    timeline.entries = [draft]
    timeline.selectEntry(7)
    const wrapper = mount(DetailPanel)
    expect(wrapper.text()).not.toContain('回信')
  })
})
