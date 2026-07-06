/**
 * Open an external URL in a new browser tab.
 *
 * Pure web mode: always uses window.open so links work in any browser
 * environment. The previous Tauri shell-plugin path has been removed.
 */
export async function openExternal(url: string): Promise<void> {
  if (!url) return
  window.open(url, '_blank', 'noopener,noreferrer')
}
