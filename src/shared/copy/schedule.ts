/** Centralized copy for the scheduled-task scene (A4). */

export const scheduleCopy = {
  title: '定时任务',
  subtitle: '让夜记在固定的时刻，替你做一件小事。',
  back: '返回',

  // Create form
  createTitle: '新建定时任务',
  kindLabel: '任务类型',
  cronLabel: '调度时间（cron）',
  cronPlaceholder: '0 22 * * *',
  cronHint: '五段式：分 时 日 月 周。如「0 22 * * *」表示每天 22:00。',
  enabledLabel: '创建后立即启用',
  create: '创建',
  creating: '创建中……',

  // List
  listTitle: '我的定时任务',
  empty: '还没有定时任务',
  emptyHint: '选一个类型，填上时间，夜记就会按时替你完成。',
  pause: '暂停',
  resume: '启用',
  trigger: '立即执行',
  edit: '改时间',
  save: '保存',
  cancel: '取消',
  delete: '删除',
  running: '执行中……',

  // Meta / receipts
  nextRun: '下次执行',
  lastRun: '上次执行',
  never: '尚未执行',
  runs: '执行回执',
  runsEmpty: '还没有执行记录',
  hideRuns: '收起回执',
  statusDone: '成功',
  statusFailed: '失败',
  statusRunning: '进行中',

  // Delete confirm
  confirmDeleteTitle: '删除这个定时任务？',
  confirmDeleteDesc: '删除后不再按时执行，历史回执也会一并移除。',
  confirmDelete: '删除',

  // Errors
  loadError: '加载定时任务失败',
  createError: '创建定时任务失败',
  updateError: '更新定时任务失败',
  deleteError: '删除定时任务失败',
  triggerError: '执行定时任务失败',

  // Fallback labels when the API does not return a kind_label.
  kinds: {
    daily_review: '每日回顾',
    weekly_insight: '每周洞察',
    plan_reminder: '计划提醒',
  } as Record<string, string>,
} as const