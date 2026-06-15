/** Centralized copy for the Memory Library ("记忆库") scene. */

export const memoryCopy = {
  title: '记忆库',
  back: '返回',
  subtitle: [
    '你不必从中得到什么。你只是没有把它丢掉——这本身已经足够。',
    '日记不是雕刻未来的凿子。它是一张不会丢下你的网。',
  ],

  // Overview
  overviewTitle: '记忆概览',
  episodicCount: (n: number) => `${n} 条情节记忆`,
  cardContribution: (n: number) => `其中 ${n} 条来自记忆卡片`,
  diaryContribution: (n: number) => `${n} 条来自日记分析`,
  profileBuilt: '长期画像已建立',
  profileEmpty: '长期画像尚未建立',

  // Long-term profile
  profileTitle: '长期画像',
  profileDesc: '随着记录增多，夜记会逐渐勾勒出你的轮廓。',
  profileEmptyHint: '多写几篇日记、做几次 AI 分析后，这里会浮现你的性格与情绪基线。',
  personalityTags: '性格标签',
  emotionBaseline: '情绪基线',
  dominantEmotion: '主导情绪',
  avgSentiment: '平均情绪',
  volatility: '情绪波动',
  importantPeople: '重要的人',
  recurringTopics: '反复出现的话题',
  responseStyle: '偏好的回应风格',
  none: '暂无',

  // Episodic
  episodicTitle: '情节记忆',
  episodicDesc: '一条条具体的事件与心情。记忆卡片会沉淀为这里的情节记忆。',
  episodicEmpty: '还没有情节记忆',
  episodicEmptyHint: '记一笔卡片，或做一次 AI 分析，事件就会留在这里。',
  sourceCard: '来自卡片',
  sourceDiary: '来自日记',
  importance: '重要性',

  // Cards section
  cardsTitle: '记忆卡片',
  cardsDesc: '卡片是最轻量的记忆原子，保存后会沉淀进上面的情节记忆。',
  goToCards: '管理记忆卡片',

  loadError: '加载记忆库失败',
} as const
