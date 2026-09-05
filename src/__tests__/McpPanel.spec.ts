import { describe, expect, it, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

vi.mock('@/shared/api/dev', () => ({
  getMcpStatus: vi.fn(async () => ({
    items: [
      {
        alias: 'tavily',
        transport: 'stdio',
        state: 'healthy',
        tool_count: 3,
        restart_count: 1,
        last_error: '',
        loaded_at: '2026-09-04T10:00:00+00:00',
      },
    ],
  })),
  getMcpTools: vi.fn(async () => ({
    items: [
      { name: 'search_diary', description: '搜索历史日记', source: 'local', transport: 'local' },
      { name: 'mcp__tavily__search', description: '联网搜索', source: 'tavily', transport: 'stdio' },
    ],
  })),
  getMcpCalls: vi.fn(async () => ({
    items: [
      {
        id: 'c1',
        user_id: 'u1',
        trace_id: 't1',
        endpoint_alias: 'tavily',
        transport: 'stdio',
        tool_name: 'mcp__tavily__search',
        raw_tool_name: 'search',
        status: 'success',
        duration_ms: 1200,
        error_message: null,
        arguments_snapshot: '{"query": "上海 天气"}',
        result_snapshot: '{"results": []}',
        created_at: 1759970000,
      },
    ],
    total: 1,
  })),
}))

import { getMcpCalls, getMcpStatus, getMcpTools } from '@/shared/api/dev'
import McpPanel from '@/features/dev/McpPanel.vue'

function mountPanel() {
  return mount(McpPanel)
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('McpPanel', () => {
  it('renders endpoint row with alias/transport/restart count', async () => {
    const wrapper = mountPanel()
    await flushPromises()
    const text = wrapper.text()
    expect(text).toContain('tavily')
    expect(text).toContain('stdio')
    expect(text).toContain('重启 1 次')
  })

  it('renders tool list with local and mcp source tags', async () => {
    const wrapper = mountPanel()
    await flushPromises()
    const text = wrapper.text()
    expect(text).toContain('mcp__tavily__search')
    expect(text).toContain('联网搜索')
    expect(text).toContain('search_diary')
  })

  it('expands a call row and emits openTrace on trace link click', async () => {
    const wrapper = mountPanel()
    await flushPromises()
    await wrapper.find('.mcp-panel__row--button').trigger('click')
    expect(wrapper.text()).toContain('上海 天气')
    await wrapper.find('.mcp-panel__trace-link').trigger('click')
    expect(wrapper.emitted('openTrace')).toEqual([['t1']])
  })

  it('reloads all three sources on refresh click', async () => {
    const wrapper = mountPanel()
    await flushPromises()
    await wrapper.find('.mcp-panel__refresh').trigger('click')
    await flushPromises()
    expect(getMcpStatus).toHaveBeenCalledTimes(2)
    expect(getMcpTools).toHaveBeenCalledTimes(2)
    expect(getMcpCalls).toHaveBeenCalledTimes(2)
  })

  it('shows empty endpoint hint when no endpoints configured', async () => {
    vi.mocked(getMcpStatus).mockResolvedValueOnce({ items: [] })
    const wrapper = mountPanel()
    await flushPromises()
    expect(wrapper.text()).toContain('未配置 MCP 端点')
  })
})
