/** Copy & presets for the standalone Models scene. */
import type { ModelTier } from '@/shared/api/models'

export interface ModelOption {
  /** API model name passed to the provider */
  value: string
  /** Display label shown in dropdown */
  label: string
}

export interface ModelPreset {
  key: string
  name: string
  description: string
  keyUrl: string
  baseUrl: string
  defaultModel: string
  suggestedTier: ModelTier
  /** Available models for this provider; empty for custom */
  models: ModelOption[]
  freeHint?: string
}

export const MODEL_PRESETS: ModelPreset[] = [
  {
    key: 'deepseek',
    name: 'DeepSeek 深度求索',
    description: '性价比高，中文表达自然，推荐作为默认模型',
    keyUrl: 'https://platform.deepseek.com/api_keys',
    baseUrl: 'https://api.deepseek.com',
    defaultModel: 'deepseek-v4-flash',
    suggestedTier: 'default',
    models: [
      { value: 'deepseek-v4-flash', label: 'V4 Flash（快速，非思考模式）' },
      { value: 'deepseek-v4-pro', label: 'V4 Pro（深度思考模式）' },
      { value: 'deepseek-chat', label: 'deepseek-chat（旧名，2026/07 停用）' },
      { value: 'deepseek-reasoner', label: 'deepseek-reasoner（旧名，2026/07 停用）' },
    ],
  },
  {
    key: 'qwen',
    name: '通义千问（百炼）',
    description: '阿里云 DashScope 兼容模式，能力均衡',
    keyUrl: 'https://bailian.console.aliyun.com/',
    baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    defaultModel: 'qwen-plus',
    suggestedTier: 'medium',
    models: [
      { value: 'qwen-plus', label: 'Qwen Plus（均衡推荐）' },
      { value: 'qwen-max', label: 'Qwen Max（旗舰）' },
      { value: 'qwen-turbo', label: 'Qwen Turbo（快速轻量）' },
      { value: 'qwen3-coder', label: 'Qwen3 Coder（编程专用）' },
    ],
  },
  {
    key: 'glm',
    name: '智谱 GLM',
    description: 'glm-4-flash 永久免费，适合轻量任务',
    keyUrl: 'https://open.bigmodel.cn/usercenter/apikeys',
    baseUrl: 'https://open.bigmodel.cn/api/paas/v4',
    defaultModel: 'glm-4-flash',
    suggestedTier: 'light',
    models: [
      { value: 'glm-4-flash', label: 'GLM-4-Flash（永久免费）' },
      { value: 'glm-4', label: 'GLM-4（标准）' },
      { value: 'glm-4-plus', label: 'GLM-4-Plus（增强）' },
      { value: 'glm-4.5', label: 'GLM-4.5' },
      { value: 'glm-4.6', label: 'GLM-4.6' },
      { value: 'glm-4.7-flash', label: 'GLM-4.7-Flash（免费）' },
    ],
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
    models: [
      { value: 'moonshot-v1-8k', label: '8K 上下文' },
      { value: 'moonshot-v1-32k', label: '32K 上下文' },
      { value: 'moonshot-v1-128k', label: '128K 上下文（长文）' },
      { value: 'moonshot-v1-auto', label: 'Auto（自动选择上下文长度）' },
    ],
  },
  {
    key: 'baichuan',
    name: '百川',
    description: '中文理解强，适合深度分析',
    keyUrl: 'https://platform.baichuan-ai.com/',
    baseUrl: 'https://api.baichuan-ai.com/v1',
    defaultModel: 'Baichuan4',
    suggestedTier: 'heavy',
    models: [
      { value: 'Baichuan4-Turbo', label: 'Baichuan4-Turbo（旗舰升级）' },
      { value: 'Baichuan4-Air', label: 'Baichuan4-Air（轻量）' },
      { value: 'Baichuan4', label: 'Baichuan4（标准）' },
      { value: 'Baichuan3-Turbo', label: 'Baichuan3-Turbo' },
      { value: 'Baichuan3-Turbo-128k', label: 'Baichuan3-Turbo-128k（长文）' },
      { value: 'Baichuan2-Turbo', label: 'Baichuan2-Turbo（经济）' },
    ],
  },
  {
    key: 'spark',
    name: '讯飞星火',
    description: 'lite 版永久免费，通用能力强',
    keyUrl: 'https://console.xfyun.cn/services/bm35',
    baseUrl: 'https://spark-api-open.xf-yun.com/v1',
    defaultModel: 'generalv3.5',
    suggestedTier: 'medium',
    models: [
      { value: 'general', label: 'Spark Lite（general，永久免费）' },
      { value: 'generalv3', label: 'Spark V3' },
      { value: 'generalv3.5', label: 'Spark V3.5（推荐）' },
      { value: '4.0Ultra', label: 'Spark 4.0 Ultra（旗舰）' },
    ],
    freeHint: 'Lite 版（general）永久免费',
  },
  {
    key: 'siliconflow',
    name: '硅基流动（聚合）',
    description: '一个 key 调用多家模型，模型名需带「厂商/」前缀',
    keyUrl: 'https://cloud.siliconflow.cn/account/ak',
    baseUrl: 'https://api.siliconflow.cn/v1',
    defaultModel: 'deepseek-ai/DeepSeek-V3',
    suggestedTier: 'default',
    models: [
      { value: 'deepseek-ai/DeepSeek-V3', label: 'DeepSeek V3' },
      { value: 'deepseek-ai/DeepSeek-R1', label: 'DeepSeek R1（推理）' },
      { value: 'Qwen/Qwen2.5-72B-Instruct', label: 'Qwen 2.5 72B' },
      { value: 'THUDM/glm-4-9b-chat', label: 'GLM-4 9B（免费）' },
    ],
  },
  {
    key: 'openai',
    name: 'OpenAI',
    description: 'gpt-4o-mini 等原生模型，需海外网络',
    keyUrl: 'https://platform.openai.com/api-keys',
    baseUrl: 'https://api.openai.com/v1',
    defaultModel: 'gpt-4o-mini',
    suggestedTier: 'heavy',
    models: [
      { value: 'gpt-4o-mini', label: 'GPT-4o mini（经济）' },
      { value: 'gpt-4o', label: 'GPT-4o（标准）' },
      { value: 'gpt-4-turbo', label: 'GPT-4 Turbo' },
      { value: 'o1-mini', label: 'o1 mini（推理）' },
    ],
  },
  {
    key: 'custom',
    name: '自定义（OpenAI 兼容）',
    description: '任意兼容 OpenAI 接口的服务，手动填写地址与模型名',
    keyUrl: '',
    baseUrl: '',
    defaultModel: '',
    suggestedTier: 'default',
    models: [],
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
  modelSelectLabel: '选择模型',
  modelInputPlaceholder: '手动输入模型名',
} as const
