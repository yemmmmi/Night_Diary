/**
 * Open an external URL in the system's default browser.
 *
 * In Tauri (packaged exe), uses the shell plugin to open the URL via the OS
 * default handler. In a regular browser (dev server), falls back to
 * window.open so the link still works during web testing.
 */
export async function openExternal(url: string): Promise<void> {
  if (!url) return

  const isTauri = typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window

  if (isTauri) {
    const { open } = await import('@tauri-apps/plugin-shell')
    await open(url)
  } else {
    window.open(url, '_blank', 'noopener,noreferrer')
  }
}
