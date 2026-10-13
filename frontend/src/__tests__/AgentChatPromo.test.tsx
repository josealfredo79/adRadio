import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import AgentChat from '@/components/AgentChat'
import { getSiteTheme } from '@/pages/publicSite/theme'

// Promo dentro del chat del cliente (docs/specs/2026-10-13-promo-en-el-chat.md).

const get = vi.fn()
const post = vi.fn()
vi.mock('@/lib/api', () => ({
  default: { get: (...a: unknown[]) => get(...a), post: (...a: unknown[]) => post(...a) },
}))
vi.mock('@/components/MascotSmart', () => ({ default: () => null }))
vi.mock('@/components/Mascot3D', () => ({ default: () => null }))
vi.mock('@/lib/useSpeaker', () => ({
  useSpeaker: () => ({ speak: vi.fn(), unlock: vi.fn(), stop: vi.fn(), speaking: false, muted: false, toggleMute: vi.fn() }),
}))

const BUSINESS = { advertiser_id: 'a1', name: 'CityCell', agent: 'Asistente', color: '#7c3aed', greeting: '' }

const PROMO_MSG = {
  id: 'promo-c1',
  kind: 'promo',
  role: 'assistant',
  content: 'Hola Tú (prueba), 2x1 en fundas esta semana en CityCell',
  channel: 'web',
  from_owner: false,
  at: new Date().toISOString(),
  promo: {
    id: 'c1',
    title: 'Fundas 2x1',
    image_url: '',
    coupon: { code: '2WTDTA3S', description: '2x1 en fundas', expires_at: '2026-10-15T20:00:00Z' },
  },
}

function renderChat(promoId?: string) {
  return render(
    <AgentChat
      business={BUSINESS}
      theme={getSiteTheme('medianoche')}
      voiceBase="/public/portal/tok"
      portalToken="tok"
      promoId={promoId}
      customerName="Tú"
      prefill={null}
      onClose={() => {}}
      layout="screen"
    />,
  )
}

const chatPosts = () => post.mock.calls.filter(([url]) => String(url).startsWith('/widget/chat/'))

describe('Promo en el chat', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    Element.prototype.scrollTo = vi.fn()
    get.mockResolvedValue({ data: { messages: [PROMO_MSG] } })
    post.mockImplementation((url: string) =>
      Promise.resolve({
        data: url.endsWith('/chat-session') ? { session_id: 's1' } : { reply: '¡Claro! Te la aparto.', session_id: 's1' },
      }),
    )
  })

  it('shows the promo as a bubble with its coupon', async () => {
    renderChat()
    expect(await screen.findByText('Hola Tú (prueba), 2x1 en fundas esta semana en CityCell')).toBeDefined()
    expect(screen.getByText('🎁 Fundas 2x1')).toBeDefined()
    expect(screen.getByText('2WTDTA3S')).toBeDefined()
    expect(screen.getByText(/Vence el/)).toBeDefined()
  })

  it('"¡La quiero!" sends the message with the promo so the bot knows which one', async () => {
    renderChat()
    fireEvent.click(await screen.findByRole('button', { name: '¡La quiero!' }))
    await waitFor(() => expect(chatPosts()).toHaveLength(1))
    const [, body] = chatPosts()[0]
    expect(body).toMatchObject({ message: '¡La quiero! — Fundas 2x1', promo_id: 'c1', portal_token: 'tok' })
    expect(await screen.findByText('¡Claro! Te la aparto.')).toBeDefined()
  })

  it('coming from the promo page, the first message carries the promo (only once)', async () => {
    renderChat('c1')
    const input = await screen.findByPlaceholderText(/Mensaje/i)
    fireEvent.change(input, { target: { value: 'Me interesa la promo' } })
    fireEvent.submit(input.closest('form')!)
    await waitFor(() => expect(chatPosts()).toHaveLength(1))
    expect(chatPosts()[0][1]).toMatchObject({ promo_id: 'c1' })

    fireEvent.change(input, { target: { value: '¿hasta cuándo?' } })
    fireEvent.submit(input.closest('form')!)
    await waitFor(() => expect(chatPosts()).toHaveLength(2))
    expect((chatPosts()[1][1] as { promo_id?: string }).promo_id).toBeUndefined()
  })
})
