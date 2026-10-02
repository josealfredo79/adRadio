import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { HelmetProvider } from 'react-helmet-async'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import VoiceSetupPage from '@/pages/VoiceSetupPage'

const post = vi.fn()
vi.mock('@/lib/api', () => ({
  default: { post: (...args: unknown[]) => post(...args) },
  getApiError: (_e: unknown, fallback: string) => fallback,
}))

const PROFILE = {
  business_category: 'barbería',
  city: 'Tlaxiaco',
  address: 'Calle Hidalgo 12',
  business_hours: { mon: ['10:00', '20:00'], tue: null, wed: null, thu: null, fri: null, sat: null, sun: null },
  services: [
    { name: 'Corte', price: 150, description: null },
    { name: 'Barba', price: 100, description: null },
  ],
  payment_methods: ['efectivo'],
  policies: [],
  faqs: [{ q: '¿Hay estacionamiento?', a: 'Uno público enfrente' }],
  notes: [],
}

function renderPage() {
  return render(
    <HelmetProvider>
      <BrowserRouter>
        <VoiceSetupPage />
      </BrowserRouter>
    </HelmetProvider>,
  )
}

describe('VoiceSetupPage', () => {
  beforeEach(() => post.mockReset())

  it('invites to talk and reassures nothing is published without approval', () => {
    renderPage()
    expect(screen.getByText('Cuéntale a tu bot de tu negocio')).toBeDefined()
    expect(screen.getByText(/No se publica nada hasta que tú lo apruebes/)).toBeDefined()
    expect(screen.getByText('Tu horario')).toBeDefined()
  })

  it('typed fallback → review → remove a service → apply', async () => {
    post.mockImplementation((url: string) => {
      if (url === '/voice-setup/listen') {
        return Promise.resolve({
          data: { transcript: 'Abrimos de 10 a 8', profile: PROFILE, hours_text: 'Lunes 10:00–20:00',
                  instructions_preview: 'Servicios…', replaces_existing_instructions: true },
        })
      }
      return Promise.resolve({ data: { products_created: 1, products_updated: 0, hours_set: true } })
    })
    renderPage()
    fireEvent.click(screen.getByText(/Prefieres escribir|escríbelo aquí/))
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Abrimos de 10 a 8, corte 150' } })
    fireEvent.click(screen.getByText('Ordenar mi información'))

    await screen.findByText('Esto es lo que entendí. ¿Está bien?')
    expect(screen.getByText('Corte')).toBeDefined()
    expect(screen.getByText(/reemplaza las instrucciones/)).toBeDefined()

    fireEvent.click(screen.getByLabelText('Quitar Barba'))
    expect(screen.queryByText('Barba')).toBeNull()

    fireEvent.click(screen.getByText('Así está bien, configura mi bot'))
    await screen.findByText('¡Listo! Tu bot quedó configurado')
    const applied = post.mock.calls.find(([url]) => url === '/voice-setup/apply')![1] as { profile: typeof PROFILE }
    expect(applied.profile.services.map((s) => s.name)).toEqual(['Corte'])
    await waitFor(() => expect(screen.getByText(/Agregamos 1 producto a tu catálogo/)).toBeDefined())
  })

  it('a correction sends the current draft', async () => {
    post.mockResolvedValue({
      data: { transcript: 'x', profile: PROFILE, hours_text: null, instructions_preview: 'algo', replaces_existing_instructions: false },
    })
    renderPage()
    fireEvent.click(screen.getByText(/Prefieres escribir|escríbelo aquí/))
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'primera versión' } })
    fireEvent.click(screen.getByText('Ordenar mi información'))
    await screen.findByText('Esto es lo que entendí. ¿Está bien?')

    fireEvent.click(screen.getByText('Escribir'))
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'el sábado cerramos a las 5' } })
    fireEvent.click(screen.getByText('Aplicar cambio'))
    await waitFor(() => expect(post).toHaveBeenCalledTimes(2))
    const form = post.mock.calls[1][1] as FormData
    expect(form.get('text')).toBe('el sábado cerramos a las 5')
    expect(JSON.parse(form.get('draft') as string).city).toBe('Tlaxiaco')
  })
})
