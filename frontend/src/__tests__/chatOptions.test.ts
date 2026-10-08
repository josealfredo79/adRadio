import { describe, expect, it } from 'vitest'
import { parseChatOptions } from '@/lib/chatOptions'

describe('parseChatOptions', () => {
  it('turns the numbered time slots into buttons, without the WhatsApp instructions', () => {
    const out = parseChatOptions(
      'Estos son los horarios disponibles:\n1) 9:00 am\n2) 9:30 am\n3) 10:00 am\n\nResponde con el número de la opción que prefieras.\n\nEscribe *MAS* para ver más horarios.'
    )
    expect(out?.text).toBe('Estos son los horarios disponibles:')
    expect(out?.options).toEqual([{ n: '1', label: '9:00 am' }, { n: '2', label: '9:30 am' }, { n: '3', label: '10:00 am' }])
    expect(out?.more).toBe(true)
  })

  it('ignores normal messages that only happen to have a numbered list', () => {
    expect(parseChatOptions('Te recomiendo:\n1) Corte\n2) Barba')).toBeNull()
    expect(parseChatOptions('¡Hola! ¿En qué te ayudo?')).toBeNull()
  })
})
