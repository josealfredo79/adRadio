import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { CampaignBuilderChat, type BuilderStep } from '@/pages/campaigns/components/CampaignBuilderChat'
import { startsAtLabel } from '@/pages/campaigns/campaignTime'

// La campaña que pregunta (docs/specs/2026-10-29-campana-que-pregunta.md): la
// pantalla solo dibuja lo que manda el backend; aquí se prueba que lo dibuje.

const post = vi.fn()
vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api')
  return { default: { post: (...a: unknown[]) => post(...a) }, getApiError: actual.getApiError }
})

const step = (over: Partial<BuilderStep>): BuilderStep => ({
  campaign_id: 'c1', step: 'what', text: '¿Qué quieres anunciar?', choices: [], input: null, preview: null, done: false, ...over,
})
const ch = (id: string, label: string, locked = false) => ({ id, label, locked })

function renderChat(initial?: BuilderStep, onDone = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={qc}><CampaignBuilderChat initial={initial} onDone={onDone} /></QueryClientProvider>)
  return onDone
}

describe('CampaignBuilderChat', () => {
  beforeEach(() => vi.clearAllMocks())

  it('caso 1: opens asking what to announce, with a text field', async () => {
    post.mockResolvedValue({ data: step({ campaign_id: null, input: 'what' }) })
    renderChat()
    expect(await screen.findByText('¿Qué quieres anunciar?')).toBeDefined()
    expect(post).toHaveBeenCalledWith('/campaigns/builder', {})
    expect(screen.getByLabelText('Tu respuesta')).toBeDefined()
  })

  it('caso 2: typing what to announce shows "¿Cómo se lo mando?" with buttons', async () => {
    post.mockResolvedValueOnce({ data: step({ campaign_id: null, input: 'what' }) })
      .mockResolvedValueOnce({ data: step({ step: 'format', text: '¿Cómo se lo mando?', choices: [ch('f:text', 'Texto'), ch('f:photo', 'Con foto'), ch('f:audio', 'Audio de radio')] }) })
    renderChat()
    await screen.findByText('¿Qué quieres anunciar?')
    fireEvent.change(screen.getByLabelText('Tu respuesta'), { target: { value: '2x1 en micas' } })
    fireEvent.click(screen.getByLabelText('Enviar'))
    expect(await screen.findByText('¿Cómo se lo mando?')).toBeDefined()
    expect(post).toHaveBeenLastCalledWith('/campaigns/builder', { campaign_id: null, text: '2x1 en micas' })
    expect(screen.getByText('2x1 en micas')).toBeDefined() // su respuesta queda como burbuja
    expect(screen.getByRole('button', { name: 'Audio de radio' })).toBeDefined()
  })

  it('caso 3: the cuña preview has a player; tapping a button sends its id', async () => {
    post.mockResolvedValue({ data: step({ step: 'audience', text: '¿A quién se la mando?', choices: [ch('a:all', 'Todos')] }) })
    renderChat(step({
      step: 'preview', text: 'Escúchala. ¿Así está bien?', choices: [ch('ok', 'Así está bien'), ch('other', 'Otra versión')],
      preview: { kind: 'audio', text: 'guion', image_url: null, audio_url: 'https://cdn.test/cuna.ogg' },
    }))
    expect(screen.getByLabelText('Tu cuña').getAttribute('src')).toBe('https://cdn.test/cuna.ogg')
    fireEvent.click(screen.getByText('Así está bien'))
    await screen.findByText('¿A quién se la mando?')
    expect(post).toHaveBeenCalledWith('/campaigns/builder', { campaign_id: 'c1', choice: 'ok' })
  })

  it('caso 4: the photo preview shows the image', () => {
    renderChat(step({
      step: 'preview', text: 'Así la ve tu cliente.',
      preview: { kind: 'image', text: '2x1 en micas', image_url: 'https://cdn.test/b.jpg', audio_url: null },
    }))
    expect(screen.getByAltText('Así se ve tu promo').getAttribute('src')).toBe('https://cdn.test/b.jpg')
  })

  it('caso 8: "Mandar gratis por web" finishes and refreshes the list', async () => {
    post.mockResolvedValue({ data: step({ step: 'done', text: '¡Listo! Tu promo va gratis por web.', done: true }) })
    const onDone = renderChat(step({ step: 'send', text: 'Le llega: a 1 cliente les suena aviso.', choices: [ch('web', 'Mandar gratis por web')] }))
    fireEvent.click(screen.getByText('Mandar gratis por web'))
    await screen.findByText('¡Listo! Tu promo va gratis por web.')
    await waitFor(() => expect(onDone).toHaveBeenCalled())
    expect(screen.queryByRole('button', { name: 'Mandar gratis por web' })).toBeNull()
  })

  it('caso 10: a locked format shows the lock', () => {
    renderChat(step({ step: 'format', text: '¿Cómo se lo mando?', choices: [ch('f:audio', '🔒 Audio de radio', true)] }))
    expect(screen.getByRole('button', { name: '🔒 Audio de radio' })).toBeDefined()
  })

  it('caso 11: "Seguir" resumes the draft without a campaign id', async () => {
    post.mockResolvedValue({ data: step({ step: 'preview', text: 'Así le llega a tu cliente.' }) })
    renderChat(step({ campaign_id: 'c9', step: 'resume', text: '¿Seguimos con tu promo «2x1 en micas»?', choices: [ch('resume:c9', 'Seguir'), ch('new', 'Empezar otra')] }))
    fireEvent.click(screen.getByText('Seguir'))
    await screen.findByText('Así le llega a tu cliente.')
    expect(post).toHaveBeenCalledWith('/campaigns/builder', { campaign_id: null, choice: 'resume:c9' })
  })

  it('caso 4: "Subir una foto" la sube y luego la elige para la promo', async () => {
    post.mockImplementation((url: string) => Promise.resolve(url === '/copilot/photo'
      ? { data: { url: 'https://cdn.test/subida.jpg' } }
      : { data: step({ step: 'preview', text: 'Así la ve tu cliente.', preview: { kind: 'image', text: '2x1 en micas', image_url: 'https://cdn.test/subida.jpg', audio_url: null } }) }))
    renderChat(step({ step: 'photo', text: '¿Con qué foto?', input: 'photo', choices: [ch('upload', 'Subir una foto'), ch('poster', 'Cartel de colores')] }))
    const file = new File(['foto'], 'mica.jpg', { type: 'image/jpeg' })
    fireEvent.change(screen.getByLabelText('Subir una foto'), { target: { files: [file] } })
    expect(await screen.findByText('Así la ve tu cliente.')).toBeDefined()
    expect(post).toHaveBeenCalledWith('/copilot/photo', expect.any(FormData))
    await waitFor(() => expect(post).toHaveBeenCalledWith('/campaigns/builder',
      { campaign_id: 'c1', choice: 'upload', text: 'https://cdn.test/subida.jpg' }))
  })

  it('caso 5: el texto se lee y "Otra versión" pide otra', async () => {
    post.mockResolvedValue({ data: step({
      step: 'preview', text: 'Así le llega a tu cliente. ¿Así está bien?',
      preview: { kind: 'text', text: 'Otra versión de micas', image_url: null, audio_url: null },
      choices: [ch('ok', 'Así está bien'), ch('other', 'Otra versión'), ch('edit', 'Cambiar el texto')],
    }) })
    renderChat(step({
      step: 'preview', text: 'Así le llega a tu cliente. ¿Así está bien?',
      preview: { kind: 'text', text: '2x1 en micas', image_url: null, audio_url: null },
      choices: [ch('ok', 'Así está bien'), ch('other', 'Otra versión'), ch('edit', 'Cambiar el texto')],
    }))
    expect(screen.getByText('2x1 en micas')).toBeDefined()
    fireEvent.click(screen.getByText('Otra versión'))
    await waitFor(() => expect(post).toHaveBeenCalledWith('/campaigns/builder', { campaign_id: 'c1', choice: 'other' }))
  })

  it('caso 6: buscar a un cliente manda lo que se escribió', async () => {
    post.mockResolvedValue({ data: step({ step: 'contact', text: '¿Cuál de ellos?', input: 'contact', choices: [ch('c:9', 'Lupe (…3182)')] }) })
    renderChat(step({ step: 'contact', text: '¿A qué cliente? Escribe su nombre o teléfono.', input: 'contact' }))
    fireEvent.change(screen.getByLabelText('Tu respuesta'), { target: { value: 'Lupe' } })
    fireEvent.click(screen.getByLabelText('Enviar'))
    expect(await screen.findByText('¿Cuál de ellos?')).toBeDefined()
    expect(post).toHaveBeenCalledWith('/campaigns/builder', { campaign_id: 'c1', text: 'Lupe' })
  })

  it('caso 7: el cupón se contesta Sí o No con su botón', async () => {
    post.mockResolvedValue({ data: step({ step: 'send', text: 'Le llega: a 1 cliente le suena aviso.' }) })
    renderChat(step({
      step: 'discount', text: 'Tu mensaje dice 10%. ¿Le pongo un cupón de 10% a cada cliente?',
      choices: [ch('d:10', 'Sí'), ch('d:0', 'No')],
    }))
    fireEvent.click(screen.getByText('No'))
    expect(await screen.findByText('Le llega: a 1 cliente le suena aviso.')).toBeDefined()
    expect(post).toHaveBeenCalledWith('/campaigns/builder', { campaign_id: 'c1', choice: 'd:0' })
  })

  it('says when a night campaign goes out, in Tlaxiaco time', () => {
    expect(startsAtLabel('2026-10-29T14:00:00+00:00', new Date('2026-10-29T04:34:00Z'))).toMatch(/^mañana a las 8:00/)
    expect(startsAtLabel('2026-11-02T14:00:00+00:00', new Date('2026-11-01T04:00:00Z'))).toMatch(/^el lunes a las 8:00/)
  })
})
