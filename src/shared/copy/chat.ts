/** Copy strings for the chat conversation feature. */
export const chatCopy = {
  tab: '会话',
  emptyTitle: '还没有会话',
  emptyDesc: '开始一场对话，和你的回信者聊聊天',
  newConversation: '新建会话',
  inputPlaceholder: '输入你想说的...',
  confirmDelete: '确定删除这个会话吗？',
  confirmDeleteDesc: '会话中的所有消息将被永久删除，此操作不可撤销。',
  cancel: '取消',
  confirm: '确认删除',
  referenceTitle: '参考上下文',
  recentDiaries: '最近日记',
  episodicMemory: '情节记忆',
  noReference: '暂无参考信息',
  outputTitle: '产出',
  generateCard: '生成卡片',
  noCards: '暂无卡片',
  cardProposal: (summary: string) =>
    `要不要我帮你把今天聊的整理成一张卡片？\n\n${summary}`,
  cardSaved: '卡片已保存到今天的日记中',
  dateDivider: (date: string) => `— ${date} —`,
  skillPlaceholder: 'skill 管理（即将推出）',
} as const
