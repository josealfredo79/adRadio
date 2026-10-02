import { fireEvent, render, screen } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import VoiceDemoSection from '@/pages/landing/components/VoiceDemoSection'
import { loadDemoDraft } from '@/lib/demoDraft'

const post = vi.fn()
const get = vi.fn()
vi.mock('@/lib/api', () => ({
  default: { post: (...a: unknown[]) => post(...a), get: (...a: unknown[]) => get(...a) },
  getApiError: (_e: unknown, fallback: string) => fallback,
}))

const line = (text: string) => ({ text, sig: 'sig' })
const PROFILE = { services: [{ name: 'Taco de pastor', price: 15, description: null }] }

describe('VoiceDemoSection (landing)', () => {
  beforeEach(() => {
    post.mockReset()
    get.mockReset()
    get.mockResolvedValue({ data: { greeting: line('¡Hola! ¿Tienes un negocio?') } })
    localStorage.clear()
  })

  it('invites without an account', async () => {
    render(<BrowserRouter><VoiceDemoSection /></BrowserRouter>)
    expect(screen.getByText('Cuéntale de tu negocio. Mira cómo contestaría tu bot.')).toBeDefined()
    expect(screen.getByText(/Sin registrarte/)).toBeDefined()
    await screen.findByText('¡Hola! ¿Tienes un negocio?')
  })

  it('shows "así contestaría tu bot" with the visitor\'s own prices and keeps the draft for signup', async () => {
    post.mockImplementation((url: string) =>
      url === '/public/voice-demo/listen'
        ? Promise.resolve({
            data: {
              profile: PROFILE, say: line('¡Muy bien!'), pending_questions: [], spoken_summary: line('Vendes…'),
              demo_chat: [
                { from: 'cliente', text: 'Hola, ¿cuánto cuesta taco de pastor?' },
                { from: 'bot', text: '¡Hola! Taco de pastor cuesta $15. ¿Te gustaría apartar? 😊' },
              ],
              closing: line('Así contestaría tu bot a tus clientes.'),
            },
          })
        : Promise.resolve({ data: new Blob() }),
    )
    render(<BrowserRouter><VoiceDemoSection /></BrowserRouter>)
    fireEvent.click(screen.getByText(/Escríbelo aquí|Prefieres escribir/))
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'taquería, el pastor a 15' } })
    fireEvent.click(screen.getByText('Enséñame mi bot'))

    await screen.findByText('¡Hola! Taco de pastor cuesta $15. ¿Te gustaría apartar? 😊')
    expect(screen.getByText('Así contestaría tu bot')).toBeDefined()
    expect(screen.getByText('Crea tu cuenta y quédatelo').closest('a')?.getAttribute('href')).toBe('/register')
    expect(loadDemoDraft()).toEqual(PROFILE)
  })
})
