/** Unified timeline scene copy. Plain Chinese in .ts files is the established pattern (see weekly.ts). */

export const timelineCopy = {
  viewDay: '日',
  viewWeek: '周',
  viewMonth: '月',
  writeDiary: '记一笔',
  retry: '重试',
  prevDay: '前一天',
  nextDay: '后一天',
  prevWeek: '前一周',
  nextWeek: '后一周',
  todayTag: '今天',
  backToToday: '回到今天',
  emptyTitle: '这一天还没有记录',
  emptyHint: '从一句话开始就好',
  emptyCta: '记一笔',
  moreRecords: (n: number) => `还有 ${n} 条记录`,
  dayDrawerTitle: (label: string, day: number) => `${label} ${day}日`,
  taskSummary: (total: number, done: number) => `今日 ${total} 项 · 已完成 ${done}`,
  taskSectionDone: '都完成了，慢慢来',
} as const
