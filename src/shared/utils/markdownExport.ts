/** Build a Markdown export for one diary entry. Pure string builder. */
export function buildDiaryMarkdown(input: {
  date: string
  content: string
  emotions: string[]
}): string {
  const parts = [`# ${input.date}`, '', input.content.trim()]
  if (input.emotions.length > 0) {
    parts.push('', `情绪：${input.emotions.join('、')}`)
  }
  return `${parts.join('\n')}\n`
}

export function diaryExportFilename(date: string): string {
  return `${date}.md`
}
