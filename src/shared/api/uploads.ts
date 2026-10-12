import { getHttpClient } from '@/shared/api/http'

export interface ImageAsset {
  id: number
  original_filename: string
  mime_type: string
  size_bytes: number
  created_at: string
}

export const MAX_IMAGE_BYTES = 10 * 1024 * 1024
export const ACCEPTED_IMAGE_TYPES = 'image/jpeg,image/png,image/webp'

/** Upload one image; the backend stores the file and returns its metadata. */
export async function uploadImage(file: File): Promise<ImageAsset> {
  const client = await getHttpClient()
  const form = new FormData()
  form.append('file', file)
  const { data } = await client.post<ImageAsset>('/api/v1/uploads/images', form)
  return data
}

/**
 * Fetch an asset's bytes as an authenticated blob and return an object URL.
 * Raw `<img src>` cannot carry the JWT header, so previews load via this call.
 */
export async function fetchImageObjectUrl(assetId: number): Promise<string> {
  const client = await getHttpClient()
  const { data } = await client.get<Blob>(`/api/v1/uploads/images/${assetId}/file`, {
    responseType: 'blob',
  })
  return URL.createObjectURL(data)
}