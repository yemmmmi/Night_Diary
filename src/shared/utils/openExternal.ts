/**
 * Open an external URL in a new browser tab.
 */
export async function openExternal(url: string): Promise<void> {
  if (!url) return
  window.open(url, '_blank', 'noopener,noreferrer')
}
