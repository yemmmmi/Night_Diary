/** Centralized copy for the weekly report ("周记") letter card. */

export const weeklyCopy = {
  generate: '生成本周周记',
  generating: '正在回顾这一周……',
  regenerate: '重新生成本周',
  emptyHint: '这一周记录了日记或记忆卡片后，就能生成一封周回信',
  letterTitle: '本周的信',
  expand: '展开全文',
  collapse: '收起',
  diaryCount: (n: number) => `${n} 篇日记`,
  cardCount: (n: number) => `${n} 张卡片`,
} as const
