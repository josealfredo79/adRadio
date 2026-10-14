import { render } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { plainChatText, renderChatText } from '@/lib/chatText'

describe('renderChatText', () => {
  it('turns the bot asterisks into bold instead of showing them', () => {
    const { container } = render(<p>{renderChatText('El plan **Negocio** cuesta *$899/mes*.')}</p>)
    expect(container.textContent).toBe('El plan Negocio cuesta $899/mes.')
    expect([...container.querySelectorAll('strong')].map((s) => s.textContent)).toEqual(['Negocio', '$899/mes'])
  })

  it('leaves a lone asterisk alone', () => {
    const { container } = render(<p>{renderChatText('5 * 3 = 15')}</p>)
    expect(container.textContent).toBe('5 * 3 = 15')
    expect(container.querySelector('strong')).toBeNull()
  })
})

describe('plainChatText', () => {
  it('drops the bold asterisks in one-line previews (Inbox list)', () => {
    expect(plainChatText('¡Genial! Confirmamos tu cupón **2WTDTA3S** para *2x1*')).toBe('¡Genial! Confirmamos tu cupón 2WTDTA3S para 2x1')
  })
})
