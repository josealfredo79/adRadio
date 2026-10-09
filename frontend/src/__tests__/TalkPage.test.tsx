import { fireEvent, render, screen } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import TalkPage from '@/pages/TalkPage'

const post = vi.fn()
vi.mock('@/lib/api', () => ({
  default: { post: (...a: unknown[]) => post(...a) },
  getApiError: (_e: unknown, fallback: string) => fallback,
}))
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ user: { business_name: 'Barbería Don Pepe' } }),
}))
vi.mock('@/components/SEO', () => ({ default: () => null }))

const PENDING = {
  transcript: 'Crea un cupón del 10 % para esta semana',
  reply: 'Antes de hacerlo, confirmemos: cupón del 10 % válido hasta el domingo.',
  actions: [],
  pending_confirmation: { confirmation_id: 'tok-1', tool: 'create_coupon', summary: 'Cupón del 10 % válido hasta el domingo.' },
}

describe('TalkPage (Habla con IaRadio)', () => {
  beforeEach(() => {
    post.mockReset()
    localStorage.clear()
  })

  it('greets the owner by business name', () => {
    render(<TalkPage />)
    expect(screen.getByText(/Hola, Barbería Don Pepe/)).toBeDefined()
  })

  it('offers to check and test the owner\'s bot', async () => {
    post.mockImplementation((url: string) =>
      url === '/copilot/voice'
        ? Promise.resolve({ data: { reply: 'Tu bot ya sabe tus precios.', actions: [], pending_confirmation: null } })
        : Promise.resolve({ data: new Blob() }),
    )
    render(<TalkPage />)
    expect(screen.getByText(/revisar y probar tu bot/)).toBeDefined()
    fireEvent.click(screen.getByText('¿Mi bot ya está listo?'))
    const form = post.mock.calls.find(([url]) => url === '/copilot/voice')?.[1] as FormData
    expect(form.get('text')).toBe('¿Mi bot ya está listo?')
    await screen.findByText('Tu bot ya sabe tus precios.')
  })

  it('asks before acting and confirms with the big "Sí" button', async () => {
    post.mockImplementation((url: string) => {
      if (url === '/copilot/voice') return Promise.resolve({ data: PENDING })
      if (url === '/copilot/confirm') {
        return Promise.resolve({
          data: { reply: 'Listo, el cupón ya está activo.', actions: [{ tool: 'create_coupon', summary: 'Cupón creado: DIEZ.' }], pending_confirmation: null },
        })
      }
      return Promise.resolve({ data: new Blob() }) // la voz
    })
    render(<TalkPage />)

    fireEvent.click(screen.getByText('Crea un cupón del 10 % para esta semana'))
    const form = post.mock.calls.find(([url]) => url === '/copilot/voice')?.[1] as FormData
    expect(form.get('text')).toBe('Crea un cupón del 10 % para esta semana')

    await screen.findByText('¿Lo hago?')
    expect(screen.getByText('Cupón del 10 % válido hasta el domingo.')).toBeDefined()

    fireEvent.click(screen.getByText('Sí, hazlo'))
    await screen.findByText('Listo, el cupón ya está activo.')
    expect(post).toHaveBeenCalledWith('/copilot/confirm', { confirmation_id: 'tok-1', approve: true })
    expect(screen.getByText('Cupón creado: DIEZ.')).toBeDefined()
    expect(screen.queryByText('¿Lo hago?')).toBeNull()
  })

  it('a spoken or typed answer while something is pending carries the confirmation id', async () => {
    post.mockImplementation((url: string) =>
      url === '/copilot/voice' ? Promise.resolve({ data: PENDING }) : Promise.resolve({ data: new Blob() }),
    )
    render(<TalkPage />)
    fireEvent.click(screen.getByText('Crea un cupón del 10 % para esta semana'))
    await screen.findByText('¿Lo hago?')

    // Sin micrófono (jsdom) la caja para escribir ya está abierta.
    const typeInstead = screen.queryByText('¿Prefieres escribir?')
    if (typeInstead) fireEvent.click(typeInstead)
    fireEvent.change(screen.getByLabelText('Escribe lo que necesitas'), { target: { value: 'sí' } })
    fireEvent.click(screen.getByText('Enviar'))
    const calls = post.mock.calls.filter(([url]) => url === '/copilot/voice')
    const second = calls[1][1] as FormData
    expect(second.get('confirmation_id')).toBe('tok-1')
    expect(JSON.parse(second.get('history') as string).length).toBe(2)
  })

  it('a product photo is uploaded and goes with the next request', async () => {
    URL.createObjectURL = vi.fn(() => 'blob:preview')
    URL.revokeObjectURL = vi.fn()
    post.mockImplementation((url: string) => {
      if (url === '/copilot/photo') return Promise.resolve({ data: { url: 'https://x/api/v1/radio/audio/products/u1/a.jpg' } })
      if (url === '/copilot/voice') return Promise.resolve({ data: PENDING })
      return Promise.resolve({ data: new Blob() })
    })
    const { container } = render(<TalkPage />)
    const input = container.querySelector('input[type=file]') as HTMLInputElement
    fireEvent.change(input, { target: { files: [new File(['jpg'], 'tinte.jpg', { type: 'image/jpeg' })] } })
    await screen.findByText('Foto lista: dime qué producto es.')
    expect((post.mock.calls.find(([u]) => u === '/copilot/photo')?.[1] as FormData).get('file')).toBeInstanceOf(File)

    fireEvent.change(screen.getByLabelText('Escribe lo que necesitas'), { target: { value: 'agrega este producto, tinte a 450' } })
    fireEvent.click(screen.getByText('Enviar'))
    const form = post.mock.calls.find(([u]) => u === '/copilot/voice')?.[1] as FormData
    expect(form.get('photo_url')).toBe('https://x/api/v1/radio/audio/products/u1/a.jpg')
    await screen.findByText('¿Lo hago?')
    expect(screen.queryByText('Foto lista: dime qué producto es.')).toBeNull()
  })
})
