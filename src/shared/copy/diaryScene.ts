/** Diary write/edit scene — Unicode escapes avoid Windows encoding corruption in .vue files. */
export const diarySceneCopy = {
  back: '\u8fd4\u56de',
  deleteDiary: '\u5220\u9664\u65e5\u8bb0',
  saving: '\u4fdd\u5b58\u4e2d\u2026',
  save: '\u4fdd\u5b58',
  wordUnit: '\u5b57',
  viewAiReply: '\u67e5\u770b\u56de\u4fe1',
  getAiReply: '\u83b7\u53d6\u56de\u4fe1',
  placeholderNew:
    '\u4eca\u5929\u60f3\u5199\u70b9\u4ec0\u4e48\uff1f\u53ef\u4ee5\u4ece\u4e00\u53e5\u8bdd\u3001\u4e00\u4e2a\u753b\u9762\u5f00\u59cb',
  placeholderContinue: '\u7ee7\u7eed\u5199\u4e0b\u53bb\u2026',
  replySectionTitle: '\u56de\u4fe1',
  loadFailed: '\u52a0\u8f7d\u65e5\u8bb0\u5931\u8d25',
  deleteFailed: '\u5220\u9664\u65e5\u8bb0\u5931\u8d25',
  confirmDeleteTitle: '\u786e\u5b9a\u5220\u9664\u8fd9\u7bc7\u65e5\u8bb0\u5417\uff1f',
  confirmDeleteDesc:
    '\u65e5\u8bb0\u5185\u5bb9\u53ca\u5173\u8054\u7684 AI \u56de\u4fe1\u5c06\u88ab\u6c38\u4e45\u5220\u9664\uff0c\u6b64\u64cd\u4f5c\u4e0d\u53ef\u64a4\u9500\u3002',
  cancel: '\u53d6\u6d88',
  confirmDelete: '\u786e\u8ba4\u5220\u9664',
} as const
