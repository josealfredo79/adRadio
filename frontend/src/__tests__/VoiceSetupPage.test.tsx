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

const HOURS_Q = { field: 'hours', text: '¿En qué horario atiendes?' }
const LOCATION_Q = { field: 'location', text: '¿Dónde está tu negocio?' }

function listenResponse(over: Record<string, unknown> = {}) {
  return {
    data: {
      transcript: 'Abrimos de 10 a 8', profile: PROFILE, next_question: null, pending_questions: [],
      say: '¡Muy bien! Ya anoté 2 servicios. Ya tengo lo principal. Revisa que esté bien.',
      spoken_summary: 'Vendes corte en 150 pesos.', hours_text: 'Lunes 10:00–20:00',
      instructions_preview: 'Servicios…', replaces_existing_instructions: true, ...over,
    },
  }
}

function mockApi(listen: () => unknown) {
  post.mockImplementation((url: string) => {
    if (url === '/voice-setup/listen') return Promise.resolve(listen())
    if (url === '/voice-setup/speak') return Promise.resolve({ data: new Blob(['x'], { type: 'audio/mpeg' }) })
    return Promise.resolve({ data: { products_created: 1, products_updated: 0, hours_set: true } })
  })
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

async function typeAndSend(textValue: string, button: string) {
  fireEvent.click(screen.getAllByText(/Prefieres escribir|escríbelo aquí|^Escribir$/)[0])
  fireEvent.change(screen.getByRole('textbox'), { target: { value: textValue } })
  fireEvent.click(screen.getByText(button))
}

describe('VoiceSetupPage', () => {
  beforeEach(() => post.mockReset())

  it('greets like a person and reassures nothing is published without approval', () => {
    renderPage()
    expect(screen.getByText(/Soy tu asistente de IaRadio/)).toBeDefined()
    expect(screen.getByRole('img', { name: 'Asistente sonriendo' })).toBeDefined()
    expect(screen.getByText(/No se publica nada hasta que tú lo apruebes/)).toBeDefined()
    expect(screen.getByText('Tu horario')).toBeDefined()
  })

  it('typed fallback → review → remove a service → apply, and the face speaks', async () => {
    mockApi(() => listenResponse())
    renderPage()
    await typeAndSend('Abrimos de 10 a 8, corte 150', 'Ordenar mi información')

    await screen.findByText('Esto es lo que entendí. ¿Está bien?')
    expect(screen.getByText(/Ya anoté 2 servicios/)).toBeDefined()
    await waitFor(() => expect(post.mock.calls.some(([url]) => url === '/voice-setup/speak')).toBe(true))
    expect(screen.getByText(/reemplaza las instrucciones/)).toBeDefined()

    fireEvent.click(screen.getByLabelText('Quitar Barba'))
    expect(screen.queryByText('Barba')).toBeNull()

    fireEvent.click(screen.getByText('Así está bien, configura mi bot'))
    await screen.findByText('¡Listo! Tu bot quedó configurado')
    expect(screen.getByRole('img', { name: 'Asistente contento' })).toBeDefined()
    const applied = post.mock.calls.find(([url]) => url === '/voice-setup/apply')![1] as { profile: typeof PROFILE }
    expect(applied.profile.services.map((s) => s.name)).toEqual(['Corte'])
  })

  it('asks what is missing, one thing at a time; skip and finish work', async () => {
    mockApi(() =>
      listenResponse({
        next_question: HOURS_Q, pending_questions: [HOURS_Q, LOCATION_Q],
        say: `¡Muy bien! Ya anoté 2 servicios. ${HOURS_Q.text}`,
      }),
    )
    renderPage()
    await typeAndSend('corte 150, barba 100', 'Ordenar mi información')

    await screen.findByText(/Ya anoté 2 servicios\. ¿En qué horario atiendes\?/)
    // Sin micrófono (jsdom) se ofrece escribir; con micrófono sería 'Tocar y responder'.
    expect(screen.getByText('Saltar pregunta')).toBeDefined()

    fireEvent.click(screen.getByText('Saltar pregunta'))
    expect(screen.getByText(/Va, lo dejamos\. ¿Dónde está tu negocio\?/)).toBeDefined()

    fireEvent.click(screen.getByText('Ya terminé'))
    await screen.findByText('Esto es lo que entendí. ¿Está bien?')
  })

  it('an answer carries the question and what was already asked, plus the draft', async () => {
    let calls = 0
    mockApi(() => {
      calls += 1
      return calls === 1
        ? listenResponse({ next_question: HOURS_Q, pending_questions: [HOURS_Q], say: HOURS_Q.text })
        : listenResponse()
    })
    renderPage()
    await typeAndSend('corte 150', 'Ordenar mi información')
    await screen.findByText('Saltar pregunta')

    await typeAndSend('de 9 a 7', 'Responder')
    await screen.findByText('Esto es lo que entendí. ¿Está bien?')
    const second = post.mock.calls.filter(([url]) => url === '/voice-setup/listen')[1][1] as FormData
    expect(second.get('text')).toBe('de 9 a 7')
    expect(second.get('question')).toBe('hours')
    expect(second.get('asked')).toBe('hours')
    expect(JSON.parse(second.get('draft') as string).city).toBe('Tlaxiaco')
  })

  it('the mute button is remembered', () => {
    renderPage()
    fireEvent.click(screen.getByLabelText('Silenciar la voz'))
    expect(screen.getByLabelText('Activar la voz')).toBeDefined()
  })
})
