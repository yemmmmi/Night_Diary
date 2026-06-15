/**
 * Emotion → Phosphor icon mapping and mixed-emotion helpers.
 *
 * Shared by MemoryCardInput, Review/Home card chips and the Memory library
 * so the preset emotions render their real Phosphor icon (not a sliced
 * character) consistently everywhere.
 */
import type { Component } from 'vue'
import {
  PhSmiley,
  PhWind,
  PhHeart,
  PhStar,
  PhFire,
  PhWarningCircle,
  PhMoon,
  PhCloudRain,
  PhQuestion,
  PhFlame,
  PhTag,
} from '@phosphor-icons/vue'

import { PRESET_EMOTIONS } from '@/shared/copy/card'

/** icon-name (as used in PRESET_EMOTIONS) → Phosphor component */
const ICON_NAME_MAP: Record<string, Component> = {
  smiley: PhSmiley,
  wind: PhWind,
  heart: PhHeart,
  star: PhStar,
  fire: PhFire,
  'warning-circle': PhWarningCircle,
  moon: PhMoon,
  'cloud-rain': PhCloudRain,
  question: PhQuestion,
  flame: PhFlame,
}

/** Lookup the Phosphor icon component for an emotion key. */
export function emotionIconFor(key: string): Component {
  const preset = PRESET_EMOTIONS.find(e => e.key === key)
  if (preset && ICON_NAME_MAP[preset.icon]) {
    return ICON_NAME_MAP[preset.icon]
  }
  // Custom emotions fall back to a neutral tag icon.
  return PhTag
}
