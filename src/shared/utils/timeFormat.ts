/**
 * 服务器时间解析：后端以 naive UTC（无 Z 后缀）序列化 created_at，
 * 直接 new Date() 会按本地时区误解析。所有展示/按日分组必须经此层。
 */

const TZ_RE = /(Z|[+-]\d{2}:?\d{2})$/

export function parseServerTime(iso: string): Date {
  if (!iso) return new Date(NaN)
  const normalized = TZ_RE.test(iso) ? iso : `${iso}Z`
  return new Date(normalized)
}

export function serverDateIso(iso: string): string {
  const date = parseServerTime(iso)
  if (Number.isNaN(date.getTime())) return ''
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

export function serverTimeLabel(iso: string): string {
  const date = parseServerTime(iso)
  if (Number.isNaN(date.getTime())) return ''
  const h = String(date.getHours()).padStart(2, '0')
  const m = String(date.getMinutes()).padStart(2, '0')
  return `${h}:${m}`
}
