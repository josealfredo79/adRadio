import type { ReactNode } from 'react'

/** Negritas al estilo WhatsApp (*así*) y Markdown (**así**), que es como
 *  escribe el bot: sin esto se ven los asteriscos. */
export function renderChatText(text: string): ReactNode[] {
  return text.split(/(\*\*[^*\n]+\*\*|\*[^*\n]+\*)/g).map((part, i) => {
    const bold = part.match(/^\*\*([^*\n]+)\*\*$/) ?? part.match(/^\*([^*\n]+)\*$/)
    return bold ? <strong key={i}>{bold[1]}</strong> : part
  })
}

/** Para vistas previas de una línea (lista del Inbox): el texto sin los
 *  asteriscos de las negritas. */
export function plainChatText(text: string): string {
  return text.replace(/\*\*([^*\n]+)\*\*/g, '$1').replace(/\*([^*\n]+)\*/g, '$1')
}
