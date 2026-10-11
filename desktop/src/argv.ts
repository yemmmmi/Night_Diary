const PREFIX = '--backend-url='

export function parseBackendUrl(argv: readonly string[]): string | undefined {
  const hit = argv.find((arg) => arg.startsWith(PREFIX))
  return hit ? hit.slice(PREFIX.length) : undefined
}