/**
 * @deprecated Use `npm run tauri dev` (managed lifecycle) or attach mode:
 *   NIGHTDIARY_DEV_BACKEND_ATTACH=1 npm run tauri dev
 *
 * Kept for scripts that only need a health probe / one-shot start hint.
 */
import { probeHealth } from './lib/dev-backend.mjs'

const PORT = Number(process.env.NIGHTDIARY_DEV_BACKEND || 8000)

if (await probeHealth(PORT)) {
  console.log(`[dev-backend] already listening on ${PORT}`)
  process.exit(0)
}

console.error(
  `[dev-backend] nothing on ${PORT}. Run:\n` +
    '  npm run tauri dev\n' +
    'or start the backend manually:\n' +
    `  cd server && python -m uvicorn app.main:app --reload --host 127.0.0.1 --port ${PORT}`,
)
process.exit(1)
