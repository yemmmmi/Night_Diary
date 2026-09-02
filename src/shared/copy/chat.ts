/** Copy strings for the chat letter exchange feature. */
export const chatCopy = {
  tab: '笔谈',
  signatureUser: '我',
  signatureNight: '夜记',
  emptyTitle: (name: string) => (name ? `${name}，这一叠信还空着` : '这一叠信还空着'),
  emptyDesc: () => '写点什么，夜记在读',
  newConversation: '另起一封',
  inputPlaceholder: '回信……',
  sendLabel: '寄出',
  confirmDelete: '删掉这一叠信？',
  confirmDeleteDesc: '往来信件将一并删去，此操作不可撤销。',
  cancel: '取消',
  confirm: '确认删除',
  noReference: '暂无可附的日记',
  pickDiary: '附上日记',
  pickDiaryHint: '最多 3 篇日记 · 3 张卡片',
  pickDiaryEmpty: '暂无可附的日记',
  pickCardSection: '卡片',
  pickCardHint: '未关联日记的独立卡',
  pickCardEmpty: '暂无可附的卡片',
  removePin: '取下这一篇',
  removeCardPin: '取下这一张',
  pickPlan: '附上计划',
  pickPlanHint: '进行中的计划 · 最多 3 个',
  pickPlanEmpty: '暂无可附的计划',
  removePlanPin: '取下这一个',
  writingLabel: '夜记正在写…',
  letterNoteCount: (count: number) => `参考了 ${count} 篇日记`,
  letterAttachNote: (cards: number, plans: number) => {
    const parts: string[] = []
    if (cards > 0) parts.push(`${cards} 张卡片`)
    if (plans > 0) parts.push(`${plans} 个计划`)
    return parts.length ? `附上 ${parts.join('、')}` : ''
  },
  generateCard: '存为记忆卡片',
  cardGenerating: '收入中…',
  cardSavedInline: '已收入记忆',
  dateDivider: (date: string) => date,
} as const
