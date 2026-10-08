import { describe, expect, it } from 'vitest'
import { speakable } from '@/lib/speakable'

describe('speakable', () => {
  it('drops emojis, links and formatting marks before speaking', () => {
    expect(speakable('¡Hola! 😊 Escribe *quiero una cita* 🚀 https://iaradio.online/c/x 👍🏽 🇲🇽')).toBe('¡Hola! Escribe quiero una cita')
  })
})
