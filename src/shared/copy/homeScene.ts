/** Home kanban scene — Unicode escapes avoid Windows encoding corruption in .vue files. */
export const homeSceneCopy = {
  title: '\u591c\u8bb0',
  streak: (days: number) => `\u5df2\u8fde\u7eed\u8bb0\u5f55 ${days} \u5929`,
  settingsAria: '\u8bbe\u7f6e',
  continueWriting: '\u7ee7\u7eed\u5199',
  writeDiary: '\u5199\u65e5\u8bb0',
  replyBanner: (name: string, count: number) =>
    name ? `${name} 给你写了 ${count} 封回信` : `有 ${count} 封回信还没有读`,
  nudge: (name: string) =>
    name ? `${name}\uff0c\u4eca\u5929\u8fd8\u6ca1\u5199\u65e5\u8bb0\uff0c\u60f3\u8bf4\u70b9\u4ec0\u4e48\uff1f` : '\u4eca\u5929\u8fd8\u6ca1\u5199\u65e5\u8bb0\uff0c\u60f3\u8bf4\u70b9\u4ec0\u4e48\uff1f',
  emptyTitle: (name: string) =>
    name ? `${name}\uff0c\u4eca\u5929\u60f3\u8bb0\u5f55\u4e9b\u4ec0\u4e48\uff1f` : '\u4eca\u5929\u60f3\u8bb0\u5f55\u4e9b\u4ec0\u4e48\uff1f',
  emptyDesc: '\u591c\u8bb0\u4f1a\u8ba4\u771f\u542c\u4f60\u8bf4\uff0c\u5e76\u5728\u4f60\u9700\u8981\u7684\u65f6\u5019\u7ed9\u4f60\u56de\u4fe1',
  emptyCta: '\u5f00\u59cb\u5199\u7b2c\u4e00\u7bc7\u65e5\u8bb0',
  prevWeek: '\u4e0a\u5468',
  nextWeek: '\u4e0b\u5468',
  retry: '\u91cd\u8bd5',
  todayTag: '\u4eca\u5929',
  moreRecords: (n: number) => `\u8fd8\u6709 ${n} \u6761\u8bb0\u5f55`,
  dayDrawerTitle: (label: string, day: number) => `${label} ${day}\u65e5`,
  footerStats: (diaryCount: string | number, analysisCount: string | number) =>
    `\u5171 ${diaryCount} \u7bc7\u65e5\u8bb0 \u00b7 ${analysisCount} \u7bc7\u5df2\u6536\u5230\u56de\u4fe1`,
  reviewLink: '\u67e5\u770b\u66f4\u591a\u65e5\u8bb0 \u2192',
} as const
