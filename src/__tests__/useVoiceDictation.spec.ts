import { afterEach, describe, expect, it, vi } from 'vitest'
import { defineComponent } from 'vue'
import { mount } from '@vue/test-utils'

import { isVoiceDictationSupported, useVoiceDictation } from '@/shared/composables/useVoiceDictation'

class FakeRecognition {
  static instances: FakeRecognition[] = []
  lang = ''
  continuous = false
  interimResults = false
  onresult: ((event: unknown) => void) | null = null
  onerror: ((event: unknown) => void) | null = null
  onend: (() => void) | null = null
  start = vi.fn()
  stop = vi.fn()

  constructor() {
    FakeRecognition.instances.push(this)
  }
}

interface SpeechWindow {
  SpeechRecognition?: unknown
  webkitSpeechRecognition?: unknown
}

function withSetup<T>(composable: () => T): T {
  let result!: T
  mount(
    defineComponent({
      setup() {
        result = composable()
        return () => null
      },
    }),
  )
  return result
}

describe('useVoiceDictation', () => {
  afterEach(() => {
    FakeRecognition.instances = []
    vi.clearAllMocks()
    delete (window as SpeechWindow).SpeechRecognition
    delete (window as SpeechWindow).webkitSpeechRecognition
  })

  it('reports support based on the available constructor', () => {
    expect(isVoiceDictationSupported()).toBe(false)
    ;(window as SpeechWindow).SpeechRecognition = FakeRecognition
    expect(isVoiceDictationSupported()).toBe(true)
  })

  it('starts recognition and forwards transcripts', () => {
    ;(window as SpeechWindow).SpeechRecognition = FakeRecognition
    const onTranscript = vi.fn()
    const dictation = withSetup(() => useVoiceDictation({ onTranscript }))

    dictation.start()
    const instance = FakeRecognition.instances.at(-1)!
    expect(instance.start).toHaveBeenCalled()
    expect(instance.lang).toBe('zh-CN')
    expect(instance.continuous).toBe(true)
    expect(dictation.listening.value).toBe(true)

    instance.onresult?.({
      resultIndex: 0,
      results: { length: 1, 0: { length: 1, 0: { transcript: '今天很好' } } },
    })
    expect(onTranscript).toHaveBeenCalledWith('今天很好')
  })

  it('toggle starts then stops listening', () => {
    ;(window as SpeechWindow).SpeechRecognition = FakeRecognition
    const dictation = withSetup(() => useVoiceDictation({ onTranscript: vi.fn() }))

    dictation.toggle()
    expect(dictation.listening.value).toBe(true)

    dictation.toggle()
    expect(dictation.listening.value).toBe(false)
  })

  it('flags unsupported environments without throwing', () => {
    const dictation = withSetup(() => useVoiceDictation({ onTranscript: vi.fn() }))
    dictation.start()
    expect(dictation.error.value).toBe('unsupported')
    expect(dictation.listening.value).toBe(false)
  })
})