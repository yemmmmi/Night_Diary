import { onUnmounted, ref } from 'vue'

/**
 * Minimal Web Speech API bindings. The API is non-standard (no lib.dom types)
 * and only available in secure contexts, so it is feature-detected at call time
 * and the diary UI degrades to a disabled control when unsupported.
 */

interface SpeechRecognitionAlternativeLike {
  transcript: string
}

interface SpeechRecognitionResultLike {
  [index: number]: SpeechRecognitionAlternativeLike
  length: number
}

interface SpeechRecognitionEventLike {
  resultIndex: number
  results: { length: number; [index: number]: SpeechRecognitionResultLike }
}

interface SpeechRecognitionErrorEventLike {
  error: string
}

interface SpeechRecognitionLike {
  lang: string
  continuous: boolean
  interimResults: boolean
  start: () => void
  stop: () => void
  onresult: ((event: SpeechRecognitionEventLike) => void) | null
  onerror: ((event: SpeechRecognitionErrorEventLike) => void) | null
  onend: (() => void) | null
}

type SpeechRecognitionCtor = new () => SpeechRecognitionLike

function getRecognitionCtor(): SpeechRecognitionCtor | null {
  if (typeof window === 'undefined') return null
  const w = window as unknown as {
    SpeechRecognition?: SpeechRecognitionCtor
    webkitSpeechRecognition?: SpeechRecognitionCtor
  }
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null
}

export function isVoiceDictationSupported(): boolean {
  return getRecognitionCtor() !== null
}

export interface VoiceDictationHandlers {
  onTranscript: (text: string) => void
  lang?: string
}

export function useVoiceDictation(handlers: VoiceDictationHandlers) {
  const listening = ref(false)
  const error = ref<string | null>(null)
  let recognition: SpeechRecognitionLike | null = null

  function start() {
    const Ctor = getRecognitionCtor()
    if (!Ctor) {
      error.value = 'unsupported'
      return
    }
    error.value = null
    recognition = new Ctor()
    recognition.lang = handlers.lang ?? 'zh-CN'
    recognition.continuous = true
    recognition.interimResults = false
    recognition.onresult = (event) => {
      let text = ''
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const alternative = event.results[i]?.[0]
        if (alternative?.transcript) text += alternative.transcript
      }
      if (text) handlers.onTranscript(text)
    }
    recognition.onerror = (event) => {
      error.value = event.error || 'error'
      listening.value = false
    }
    recognition.onend = () => {
      listening.value = false
    }
    recognition.start()
    listening.value = true
  }

  function stop() {
    recognition?.stop()
    recognition = null
    listening.value = false
  }

  function toggle() {
    if (listening.value) stop()
    else start()
  }

  onUnmounted(stop)

  return { listening, error, start, stop, toggle }
}