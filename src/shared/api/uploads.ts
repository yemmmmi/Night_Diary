import { getHttpClient } from '@/shared/api/http'

export interface ImageAsset {
  id: number
  original_filename: string
  mime_type: string
  size_bytes: number
  content_type: string
  processing_path: 'pending' | 'vlm' | 'ocr_fallback' | 'skipped'
  semantic_description: string | null
  extracted_text: string | null
  processed_at: string | null
}

/**
 * Upload an image file. Returns the asset row (processing is async — poll
 * `getImageAsset` or watch `processing_path` until it leaves "pending").
 */
export async function uploadImage(file: File): Promise<ImageAsset> {
  const client = await getHttpClient()
  const form = new FormData()
  form.append('file', file)
  const { data } = await client.post<ImageAsset>('/api/v1/uploads/images', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

/** Fetch the (possibly still-pending) processing result for an asset. */
export async function getImageAsset(assetId: number): Promise<ImageAsset> {
  const client = await getHttpClient()
  const { data } = await client.get<ImageAsset>(`/api/v1/uploads/images/${assetId}`)
  return data
}

/** URL for the raw image file stream (use as <img :src>). */
export function imageUrl(assetId: number): string {
  return `/api/v1/uploads/images/${assetId}/file`
}
