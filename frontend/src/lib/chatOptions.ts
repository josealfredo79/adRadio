// El bot manda opciones numeradas para WhatsApp ("1) 9:00 am … Responde con
// el número de la opción que prefieras. Escribe *MAS* para ver más horarios").
// En el chat web se vuelven botones: tocar uno manda su número.
export interface ChatOptions {
  text: string
  options: { n: string; label: string }[]
  more: boolean
}

const OPTION_RE = /^\s*(\d{1,2})\)\s+(.+?)\s*$/
const PICK_HINT_RE = /^\s*(responde con el número|elige un número)/i
const MORE_HINT_RE = /^\s*escribe \*?mas\*? para ver más/i

export function parseChatOptions(content: string): ChatOptions | null {
  const lines = content.split('\n')
  const options = lines.map((l) => l.match(OPTION_RE)).filter(Boolean).map((m) => ({ n: m![1], label: m![2] }))
  const asksToPick = lines.some((l) => PICK_HINT_RE.test(l))
  if (options.length < 2 || !asksToPick) return null
  const more = lines.some((l) => MORE_HINT_RE.test(l))
  const text = lines
    .filter((l) => !OPTION_RE.test(l) && !PICK_HINT_RE.test(l) && !MORE_HINT_RE.test(l))
    .join('\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
  return { text, options, more }
}
