import { watch } from 'vue'

import { useSettingsStore } from '@/stores/settings'

let audioContext: AudioContext | null = null

function getAudioContext(): AudioContext | null {
  if (typeof window === 'undefined') return null
  if (!audioContext) {
    audioContext = new AudioContext()
  }
  return audioContext
}

function playTone(frequency: number, durationMs: number, volume = 0.04) {
  const settings = useSettingsStore()
  settings.load()
  if (!settings.soundEnabled) return

  const ctx = getAudioContext()
  if (!ctx) return

  const oscillator = ctx.createOscillator()
  const gain = ctx.createGain()
  oscillator.type = 'sine'
  oscillator.frequency.value = frequency
  gain.gain.value = volume
  oscillator.connect(gain)
  gain.connect(ctx.destination)
  oscillator.start()
  oscillator.stop(ctx.currentTime + durationMs / 1000)
}

export function useSound() {
  const settings = useSettingsStore()

  function playClick() {
    playTone(520, 60)
  }

  function playSuccess() {
    playTone(660, 90)
  }

  return {
    soundEnabled: settings.soundEnabled,
    playClick,
    playSuccess,
  }
}

export function bindSoundSettingWatcher() {
  const settings = useSettingsStore()
  settings.load()
  watch(
    () => settings.soundEnabled,
    (enabled) => {
      if (enabled) {
        void getAudioContext()?.resume()
      }
    },
  )
}
