import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import AgentChat from '@/components/AgentChat'
import { getSiteTheme } from '@/pages/publicSite/theme'

// "🔔 Avísame" tras la tarjeta de un producto
// (docs/specs/2026-11-10-avisame-y-segundo-recordatorio.md, casos 1-5).

const get = vi.fn()
const post = vi.fn()
vi.mock('@/lib/api', () => ({
  default: { get: (...a: unknown[]) => get(...a), post: (...a: unknown[]) => post(...a) },
  getApiError: () => 'error',
}))
vi.mock('@/components/MascotSmart', () => ({ default: () => null }))
vi.mock('@/components/Mascot3D', () => ({ default: () => null }))
vi.mock('@/lib/useSpeaker', () => ({
  useSpeaker: () => ({ speak: vi.fn(), unlock: vi.fn(), stop: vi.fn(), speaking: false, muted: false, toggleMute: vi.fn() }),
}))
const notify = vi.hoisted(() => ({ state: 'off' as string, enable: vi.fn() }))
vi.mock('@/lib/webPushClient', () => ({
  detectNotifyState: () => notify.state,
  enablePush: (...a: unknown[]) => notify.enable(...a),
}))
// El registro con código ya tiene sus pruebas: aquí solo "se verifica".
vi.mock('@/components/InlineJoin', () => ({
  default: ({ onVerified }: { onVerified: (t: string, n: string) => void }) => (
    <button onClick={() => onVerified('tok-new', 'Ana')}>verificar código</button>
  ),
}))

const BUSINESS = { advertiser_id: 'a1', name: 'CityCell', agent: 'Asistente', color: '#7c3aed', greeting: '' }
const CARD = { name: 'Cargador marca', price: '$120', url: '/p/1', photo_url: '' }
const ASK = '¿Te aviso por aquí de esto y de las promos?'

function renderChat(portalToken?: string) {
  return render(
    <AgentChat
      business={BUSINESS}
      theme={getSiteTheme('medianoche')}
      voiceBase={portalToken ? `/public/portal/${portalToken}` : '/public/site/citycell'}
      portalToken={portalToken}
      joinPath="/q/citycell"
      customerName="Ana"
      prefill={null}
      onClose={() => {}}
      layout="screen"
    />,
  )
}

async function ask(text: string) {
  fireEvent.change(await screen.findByPlaceholderText('Mensaje'), { target: { value: text } })
  fireEvent.click(screen.getByLabelText('Enviar'))
}

describe('Avísame tras un producto', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    Element.prototype.scrollTo = vi.fn()
    Element.prototype.scrollIntoView = vi.fn()
    notify.state = 'off'
    notify.enable.mockResolvedValue({ state: 'on', stamped: false })
    get.mockImplementation((url: string) =>
      Promise.resolve({
        data: url.endsWith('/messages') || url.includes('/history')
          ? { messages: [] }
          : { messages: [], push: { available: true, public_key: 'pk' } },
      }),
    )
    post.mockImplementation((url: string) =>
      Promise.resolve({
        data: url.endsWith('/chat-session')
          ? { session_id: 's1' }
          : { reply: 'El cargador cuesta $120.', session_id: 's1', cards: [CARD] },
      }),
    )
  })

  it('offers_notify_after_product_card (casos 1 y 2)', async () => {
    renderChat('tok')
    await ask('¿cuánto cuesta el cargador?')
    expect(await screen.findByText(ASK)).toBeDefined()
    fireEvent.click(screen.getByRole('button', { name: /Sí, avísame/ }))
    await waitFor(() => expect(notify.enable).toHaveBeenCalledWith('tok', 'pk'))
    expect(await screen.findByText(/Listo, te aviso al celular/)).toBeDefined()
  })

  it('anonymous_avisame_opens_join_then_offers_notify (caso 3)', async () => {
    renderChat()
    await ask('¿cuánto cuesta el cargador?')
    fireEvent.click(await screen.findByRole('button', { name: '🔔 Avísame' }))
    fireEvent.click(await screen.findByRole('button', { name: 'verificar código' }))
    // Ya verificado: la oferta de siempre, con su token nuevo.
    fireEvent.click(await screen.findByRole('button', { name: /Sí, avísame/ }))
    await waitFor(() => expect(notify.enable).toHaveBeenCalledWith('tok-new', 'pk'))
  })

  it.each(['on', 'unsupported', 'ios-install', 'denied'])('no_offer_when_on_or_unsupported (caso 4): %s', async (state) => {
    notify.state = state
    renderChat('tok')
    await ask('¿cuánto cuesta el cargador?')
    expect(await screen.findByText('El cargador cuesta $120.')).toBeDefined()
    await new Promise((r) => setTimeout(r, 30))
    expect(screen.queryByText(ASK)).toBeNull()
  })

  it.each(['on', 'unsupported', 'ios-install'])('no_offer_when_on_or_unsupported anónimo (caso 4): %s', async (state) => {
    notify.state = state
    renderChat()
    await ask('¿cuánto cuesta el cargador?')
    expect(await screen.findByText('El cargador cuesta $120.')).toBeDefined()
    await new Promise((r) => setTimeout(r, 30))
    expect(screen.queryByRole('button', { name: '🔔 Avísame' })).toBeNull()
  })

  it('offer_shows_once_per_chat (caso 5)', async () => {
    renderChat('tok')
    await ask('¿cuánto cuesta el cargador?')
    expect(await screen.findByText(ASK)).toBeDefined()
    await ask('¿y el otro cargador?')
    await waitFor(() => expect(screen.getAllByText('El cargador cuesta $120.')).toHaveLength(2))
    expect(screen.getAllByText(ASK)).toHaveLength(1)
    fireEvent.click(screen.getByRole('button', { name: 'Ahora no' }))
    expect(screen.queryByText(ASK)).toBeNull()
  })
})
