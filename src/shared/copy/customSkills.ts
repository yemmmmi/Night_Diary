/** Centralized copy for the custom-skills editor (A2). */

export const customSkillsCopy = {
  sectionTitle: '自定义技能',
  sectionSubtitle: '用你自己的话，定义夜记在这类话题里的回信偏好',

  intro:
    '技能只影响回信的语气与侧重点，不会改变全局底线，也不会让夜记执行任何操作。',
  reviewHint: '保存前会做一次安全审查：不得改变全局语气、施压或指示执行动作。',

  empty: '还没有自定义技能',
  emptyHint: '例如：当我说到「跑步」时，多问一句配速。',

  nameLabel: '技能名称',
  namePlaceholder: '如：跑步复盘',
  descriptionLabel: '一句话描述（可选）',
  descriptionPlaceholder: '如：记录跑步时更关注配速',
  triggersLabel: '触发词',
  triggersPlaceholder: '用逗号分隔，如：跑步, 配速',
  triggersHint: '当消息里出现任一触发词时，这个技能就会生效。',
  instructionLabel: '回信偏好',
  instructionPlaceholder: '如：先问一句配速，再给一句鼓励。',
  enabledLabel: '启用',

  create: '新建技能',
  save: '保存',
  saving: '保存中……',
  cancel: '取消',
  edit: '编辑',
  delete: '删除',
  enable: '启用',
  disable: '暂停',

  // Delete confirm
  confirmDeleteTitle: '删除这个技能？',
  confirmDeleteDesc: '删除后不再生效，历史版本也会一并移除。',
  confirmDelete: '删除',

  // Errors
  loadError: '加载自定义技能失败',
  createError: '创建自定义技能失败',
  updateError: '更新自定义技能失败',
  deleteError: '删除自定义技能失败',
} as const