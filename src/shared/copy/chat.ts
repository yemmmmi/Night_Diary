/** Copy strings for the chat conversation feature. */
export const chatCopy = {
  tab: '会话',
  emptyTitle: (name: string) =>
    name ? `${name}\uff0c\u8fd8\u6ca1\u6709\u4f1a\u8bdd\u54e6` : '\u8fd8\u6ca1\u6709\u4f1a\u8bdd',
  emptyDesc: (name: string) =>
    name ? `\u548c ${name} \u804a\u804a\u5929\u5427` : '\u5f00\u59cb\u4e00\u573a\u5bf9\u8bdd\uff0c\u548c\u4f60\u7684\u56de\u4fe1\u8005\u804a\u804a\u5929',
  newConversation: '新建会话',
  inputPlaceholder: '输入你想说的...',
  confirmDelete: '确定删除这个会话吗？',
  confirmDeleteDesc: '会话中的所有消息将被永久删除，此操作不可撤销。',
  cancel: '取消',
  confirm: '确认删除',
  referenceTitle: '参考上下文',
  pinnedDiaries: '引用的日记',
  retrievedDiaries: '自动检索',
  episodicMemory: '情节记忆',
  noReference: '暂无参考信息',
  pickDiary: '想聊聊什么？',
  pickDiaryHint: '最多 3 篇',
  pickDiaryEmpty: '暂无可引用的日记',
  removePin: '取消引用',
  thinkingLabel: '正在想怎么回你…',
  messageReferences: '参考了',
  outputTitle: '产出',
  generateCard: '生成卡片',
  noCards: '暂无卡片',
  cardProposal: (summary: string) =>
    `要不要我帮你把今天聊的整理成一张卡片？\n\n${summary}`,
  cardSaved: '卡片已保存到今天的日记中',
  dateDivider: (date: string) => `— ${date} —`,
  skillPlaceholder: 'skill 管理（即将推出）',
} as const

export interface DiaryReferenceItem {
  id: number
  date: string | null
  summary: string
}
