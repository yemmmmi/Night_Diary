/** Centralized copy for memory card UI components. */

export const cardCopy = {
  /** Card input component */
  newCard: '记一笔',
  quickMode: '极速',
  standardMode: '标准',
  guidedMode: '引导',
  saveCard: '保存卡片',
  cardSaved: '已保存',
  emotionLabel: '今天的心情',
  emotionPlaceholder: '选择或输入你的情绪……',
  eventLabel: '发生了什么',
  eventPlaceholder: '用一两句话概括今天的关键事件……',
  tagsLabel: '标签',
  tagsPlaceholder: '添加标签……',
  customEmotion: '自定义',
  customEmotionPlaceholder: '输入自定义情绪……',
  customTag: '自定义',
  customTagPlaceholder: '输入自定义标签……',
  expandToDiary: '展开为日记',
  expandConfirm: '将这张卡片展开为完整日记？',
  expanding: '展开中……',
  expanded: '已展开',
  cardDeleted: '卡片已删除',
  emptyCards: '还没有记忆卡片',
  emptyCardsHint: '点下方按钮，花 30 秒记录今天的心情吧',
  recentCards: '最近记忆卡片',
  recordedMoodOnly: '记录了心情',
  loadError: '加载卡片失败',
  saveError: '保存卡片失败',
  deleteError: '删除卡片失败',
  expandError: '展开卡片失败',

  /** Mood scores for quick mode */
  moodHigh: '不错',
  moodMid: '一般',
  moodLow: '不好',

  /** Card types */
  cardTypeQuick: '极速',
  cardTypeStandard: '标准',
  cardTypeGuided: '引导',

  /** Tags */
  tagWork: '工作',
  tagFamily: '家人',
  tagHealth: '健康',
  tagSocial: '社交',
  tagHobby: '爱好',
  tagStudy: '学习',
  tagRest: '休息',
  tagOther: '其他',

  /** Guided mode questions */
  guidedQuestion1: '今天最让你印象深刻的一件事是什么？',
  guidedQuestion2: '这件事给你带来了什么感受？',
  guidedQuestion3: '如果可以重来，你会怎么做？',

  /** Card-expanded diary continuation */
  cardOriginBadge: '从记忆卡片展开',
  cardDiaryPlaceholder: '从上面的一个感受开始写，也可以直接继续补充细节……',
  eventNoteLabel: '当时发生了什么',
} as const

const EMOTION_PROMPTS: Record<string, string> = {
  开心: '这份开心是从什么时候开始的？',
  平静: '是什么让你感到平静？',
  感激: '你想感谢谁，或感谢什么？',
  期待: '你在期待什么？',
  兴奋: '是什么让你兴奋起来？',
  焦虑: '这份焦虑主要来自哪里？',
  疲惫: '疲惫是从哪一刻开始的？',
  悲伤: '此刻最让你难过的是什么？',
  迷茫: '你在迷茫什么？',
  愤怒: '是什么触发了这份愤怒？',
}

export function emotionPromptFor(emotion: string): string {
  return EMOTION_PROMPTS[emotion] ?? `此刻的「${emotion}」背后，发生了什么？`
}

/** Preset emotions with Phosphor icon names */
export const PRESET_EMOTIONS = [
  { key: '开心', icon: 'smiley', moodScore: 0.85 },
  { key: '平静', icon: 'wind', moodScore: 0.65 },
  { key: '感激', icon: 'heart', moodScore: 0.8 },
  { key: '期待', icon: 'star', moodScore: 0.75 },
  { key: '兴奋', icon: 'fire', moodScore: 0.9 },
  { key: '焦虑', icon: 'warning-circle', moodScore: 0.35 },
  { key: '疲惫', icon: 'moon', moodScore: 0.3 },
  { key: '悲伤', icon: 'cloud-rain', moodScore: 0.2 },
  { key: '迷茫', icon: 'question', moodScore: 0.4 },
  { key: '愤怒', icon: 'flame', moodScore: 0.15 },
] as const

export const QUICK_TAGS = [
  { key: '工作', icon: 'briefcase' },
  { key: '家人', icon: 'users' },
  { key: '健康', icon: 'heartbeat' },
  { key: '社交', icon: 'chat-circle' },
  { key: '爱好', icon: 'palette' },
  { key: '学习', icon: 'book-open' },
  { key: '休息', icon: 'bed' },
] as const
