/** Centralized copy for the OpenAI-compatible access panel (A5). */

export const openaiAccessCopy = {
  sectionTitle: 'API 接入',
  sectionSubtitle: '把夜记接到你自己的客户端',

  intro:
    '夜记提供一个 OpenAI 兼容的接口，任何支持自定义端点的客户端都可以接入，回信仍由夜记的语气、检索与安全策略生成。',
  chatLabel: '对话补全',
  modelsLabel: '模型列表',
  authHint: '用你的登录令牌作为 API Key：请求头 Authorization: Bearer <token>。',
  featureHint: '支持流式（stream=true）与非流式；模型名可任意填写。',

  copy: '复制',
  copied: '已复制',
} as const