import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { isAxiosError } from 'axios'

import {
  deleteAnalysis,
  getAnalysis,
  regenerateAnalysis,
  triggerAnalysis,
  triggerAnalysisStreaming,
  type AnalysisRecord,
  type AnalysisTriggerPayload,
} from '@/shared/api/analysis'
import { formatApiError } from '@/shared/utils/apiError'
import { resolveBackendBaseUrl } from '@/shared/composables/useBackend'
import { useStreamingReply } from '@/shared/composables/useStreamingReply'
import { useSettingsStore } from '@/stores/settings'

export const useAnalysisStore = defineStore('analysis', () => {
  const current = ref<AnalysisRecord | null>(null)
  const loading = ref(false)
  const triggering = ref(false)
  const error = ref<string | null>(null)

  const deleting = ref(false)

  // === 流式状态 ===
  // useStreamingReply 内部使用 onUnmounted，在 setup store（函数形式的
  // defineStore）中调用是安全的：store 在首次访问时初始化，通常处于某个
  // 组件的 setup 上下文。streamingReply 提供 replyText / status 给 UI 直接
  // 消费（和 chat store 的模式一致）。
  const streamingReply = useStreamingReply()
  // 记录当前流式触发对应的 diaryId，用于 REPLY_END 后刷新完整记录。
  const streamingDiaryId = ref<number | null>(null)

  /**
   * 监听流式状态：当 status 变为 'done'（REPLY_END）时，拉取完整的
   * AnalysisRecord（含 token 统计），因为流式文本本身不带这些字段。
   */
  watch(
    () => streamingReply.status.value,
    async (newStatus, oldStatus) => {
      if (newStatus !== 'done' || oldStatus === 'done') return
      const diaryId = streamingDiaryId.value
      if (diaryId === null) return
      streamingDiaryId.value = null
      try {
        current.value = await getAnalysis(diaryId)
      } catch {
        // 流式文本已展示，刷新失败不影响已有内容；triggering 仍需复位。
      } finally {
        triggering.value = false
        streamingReply.disconnect()
      }
    },
  )

  function getReplierPayload(): AnalysisTriggerPayload {
    const settings = useSettingsStore()
    settings.load()
    const preset = settings.replierPreset
    const persona = settings.replierPersona
    const active = settings.activeReplier
    return {
      ...(preset ? { replier_preset: preset } : {}),
      ...(active?.type === 'user' && persona ? { replier_persona: persona } : {}),
    }
  }

  async function loadForDiary(diaryId: number): Promise<AnalysisRecord | null> {
    loading.value = true
    error.value = null
    try {
      current.value = await getAnalysis(diaryId)
      return current.value
    } catch (err) {
      if (isAxiosError(err) && err.response?.status === 404) {
        current.value = null
        return null
      }
      error.value = formatApiError(err, '加载分析结果失败')
      throw err
    } finally {
      loading.value = false
    }
  }

  async function triggerForDiary(diaryId: number): Promise<AnalysisRecord> {
    triggering.value = true
    error.value = null
    try {
      current.value = await triggerAnalysis(diaryId, getReplierPayload())
      return current.value
    } catch (err) {
      error.value = formatApiError(err, 'AI 分析失败')
      throw err
    } finally {
      triggering.value = false
    }
  }

  /**
   * 流式触发场景一分析。
   *
   * 调用后端 `POST /analysis/{id}/stream`，拿到 trace_id 后连接 SSE。
   * 流式期间 UI 通过 `streamingReply.replyText` 渲染打字机效果。
   * REPLY_END 后由 watch 自动 `getAnalysis` 刷新完整记录（含 token 统计）。
   *
   * 若后端返回 `streaming: false`（灰度关闭），自动回退到同步
   * `triggerForDiary`；若流式端点本身报错，同样回退到同步路径。
   */
  async function triggerForDiaryStreaming(
    diaryId: number,
  ): Promise<AnalysisRecord | null> {
    triggering.value = true
    error.value = null
    try {
      const result = await triggerAnalysisStreaming(diaryId, getReplierPayload())
      if (!result.streaming || !result.trace_id) {
        // 后端不支持流式 → 回退到同步路径（triggerForDiary 会自行管理
        // triggering 标志，注意它在本函数开头已置 true，但 triggerForDiary
        // 的 try/finally 会正确复位）。
        triggering.value = false
        return await triggerForDiary(diaryId)
      }
      // 连接 SSE 推送
      streamingDiaryId.value = diaryId
      const baseURL = await resolveBackendBaseUrl()
      streamingReply.connect(
        `${baseURL}/api/v1/dev/traces/${result.trace_id}/stream`,
      )
      return null
    } catch (err) {
      // 流式端点报错 → 回退到同步路径（不让前端卡死）
      streamingDiaryId.value = null
      triggering.value = false
      try {
        return await triggerForDiary(diaryId)
      } catch {
        // 同步路径也失败 → 暴露原始流式错误
        error.value = formatApiError(err, 'AI 分析失败')
        throw err
      }
    }
  }

  async function regenerateForDiary(diaryId: number): Promise<AnalysisRecord> {
    triggering.value = true
    error.value = null
    try {
      current.value = await regenerateAnalysis(diaryId, getReplierPayload())
      return current.value
    } catch (err) {
      error.value = formatApiError(err, '重新生成回信失败')
      throw err
    } finally {
      triggering.value = false
    }
  }

  async function removeForDiary(diaryId: number): Promise<void> {
    deleting.value = true
    error.value = null
    try {
      await deleteAnalysis(diaryId)
      current.value = null
    } catch (err) {
      error.value = formatApiError(err, '删除回信失败')
      throw err
    } finally {
      deleting.value = false
    }
  }

  function clear() {
    current.value = null
    error.value = null
  }

  return {
    current,
    loading,
    triggering,
    deleting,
    error,
    streamingReply,
    streamingDiaryId,
    loadForDiary,
    triggerForDiary,
    triggerForDiaryStreaming,
    regenerateForDiary,
    removeForDiary,
    clear,
  }
})
