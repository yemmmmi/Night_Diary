/** Copy & presets for the standalone Models scene. */
import type { ModelTier } from '@/shared/api/models'

export interface ModelPreset {
  key: string
  name: string
  description: string
  keyUrl: string
  baseUrl: string
  defaultModel: string
  suggestedTier: ModelTier
  freeHint?: string
}

export const MODEL_PRESETS: ModelPreset[] = [
  {
    key: 'deepseek',
    name: 'DeepSeek 深度求索',
    description: '性价比高，中文表达自然，推荐作为默认模型',
    keyUrl: 'https://platform.deepseek.com/api_keys',
    baseUrl: 'https://api.deepseek.com/v1',
    defaultModel: 'deepseek-chat',
    suggestedTier: 'default',
  },
  {
    key: 'qwen',
    name: '通义千问（百炼）',
    description: '阿里云 DashScope 兼容模式，能力均衡',
    keyUrl: 'https://bailian.console.aliyun.com/',
    baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    defaultModel: 'qwen-plus',
    suggestedTier: 'medium',
  },
  {
    key: 'glm',
    name: '智谱 GLM',
    description: 'glm-4-flash 永久免费，适合轻量任务',
    keyUrl: 'https://open.bigmodel.cn/usercenter/apikeys',
    baseUrl: 'https://open.bigmodel.cn/api/paas/v4',
    defaultModel: 'glm-4-flash',
    suggestedTier: 'light',
    freeHint: 'glm-4-flash 永久免费',
  },
  {
    key: 'kimi',
    name: '月之暗面 Kimi',
    description: '长上下文，适合回顾与周记总结',
    keyUrl: 'https://platform.moonshot.cn/console/api-keys',
    baseUrl: 'https://api.moonshot.cn/v1',
    defaultModel: 'moonshot-v1-8k',
    suggestedTier: 'medium',
  },
  {
    key: 'baichuan',
    name: '百川',
    description: '中文理解强，适合深度分析',
    keyUrl: 'https://platform.baichuan-ai.com/',
    baseUrl: 'https://api.baichuan-ai.com/v1',
    defaultModel: 'Baichuan4',
    suggestedTier: 'heavy',
  },
  {
    key: 'spark',
    name: '讯飞星火',
    description: 'lite 版永久免费，通用能力强',
    keyUrl: 'https://console.xfyun.cn/services/bm35',
    baseUrl: 'https://spark-api-open.xf-yun.com/v1',
    defaultModel: 'generalv3.5',
    suggestedTier: 'medium',
    freeHint: 'lite 版（general）永久免费',
  },
  {
    key: 'siliconflow',
    name: '硅基流动（聚合）',
    description: '一个 key 调用多家模型，模型名需带「厂商/」前缀',
    keyUrl: 'https://cloud.siliconflow.cn/account/ak',
    baseUrl: 'https://api.siliconflow.cn/v1',
    defaultModel: 'deepseek-ai/DeepSeek-V3',
    suggestedTier: 'default',
  },
  {
    key: 'openai',
    name: 'OpenAI',
    description: 'gpt-4o-mini 等原生模型，需海外网络',
    keyUrl: 'https://platform.openai.com/api-keys',
    baseUrl: 'https://api.openai.com/v1',
    defaultModel: 'gpt-4o-mini',
    suggestedTier: 'heavy',
  },
  {
    key: 'custom',
    name: '自定义（OpenAI 兼容）',
    description: '任意兼容 OpenAI 接口的服务，手动填写地址与模型名',
    keyUrl: '',
    baseUrl: '',
    defaultModel: '',
    suggestedTier: 'default',
  },
]

export const modelsCopy = {
  tab: '模型',
  pageTitle: 'AI 模型',
  pageSubtitle: '配置模型 API，日记回信与对话都从这里发出',
  presetSectionTitle: '快速选择',
  presetSectionHint: '点击下方厂商，自动填入地址与推荐模型，只需粘贴你的 API Key',
  getKey: '获取 Key',
  statusEmpty: '尚未配置任何 AI 模型，AI 回信将使用降级模板',
} as const
