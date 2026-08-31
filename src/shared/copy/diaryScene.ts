/** Diary write/edit scene — Unicode escapes avoid Windows encoding corruption in .vue files. */
export const diarySceneCopy = {
  back: '返回',
  close: '合上',
  deleteDiary: '删除日记',
  deleteEntry: '删除这篇',
  exportMarkdown: '导出 Markdown',
  saving: '保存中…',
  save: '保存',
  wordUnit: '字',
  placeholderNew:
    '今天想写点什么？可以从一句话、一个画面开始',
  placeholderContinue: '继续写下去…',
  loadFailed: '加载日记失败',
  deleteFailed: '删除日记失败',
  exportFailed: '导出失败',
  confirmDeleteTitle: '确定删除这篇日记吗？',
  confirmDeleteDesc:
    '日记内容将被永久删除，此操作不可撤销。',
  cancel: '取消',
  confirmDelete: '确认删除',
} as const
