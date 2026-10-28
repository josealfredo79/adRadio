import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { AxiosError, AxiosHeaders } from 'axios'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QuickCampaignModal } from '@/pages/campaigns/components/QuickCampaignModal'
import { buildCampaignBody, campaignName, webReachLine } from '@/pages/campaigns/quickCampaign'

// Campaña en 3 toques (docs/specs/2026-10-28-campana-3-toques.md).

const get = vi.fn()
const post = vi.fn()
const patch = vi.fn()
vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api')
  return {
    default: { get: (...a: unknown[]) => get(...a), post: (...a: unknown[]) => post(...a), patch: (...a: unknown[]) => patch(...a) },
    getApiError: actual.getApiError,
  }
})
vi.mock('@/contexts/ToastContext', () => ({ useToast: () => ({ toast: vi.fn() }) }))

const REACH = { total: 4, web: 1, web_silent: 0, web_chat: 3, whatsapp: 0, whatsapp_cost_mxn: 0, whatsapp_connected: false, whatsapp_unreachable: 3 }

function mockApi(reach: Record<string, unknown> = {}, opts: { resumeFails?: boolean } = {}) {
  post.mockImplementation((url: string, body: unknown) => {
    if (url === '/campaigns/generate-content') {
      return Promise.resolve({ data: { variants: ['Hola {{nombre}}, 2x1 en tacos de $40 en {{negocio}}', 'Versión dos'] } })
    }
    if (url === '/campaigns/reach-preview') return Promise.resolve({ data: { ...REACH, ...reach, _segment: body } })
    if (url === '/campaigns') return Promise.resolve({ data: { id: 'camp-1' } })
    if (url === '/campaigns/camp-1/resume') {
      if (opts.resumeFails) {
        const err = new AxiosError('x', '409', undefined, undefined, {
          status: 409, statusText: '', headers: {}, config: { headers: new AxiosHeaders() },
          data: { detail: 'Esta lista ya recibió una campaña hace poco.' },
        })
        return Promise.reject(err)
      }
      return Promise.resolve({ data: { message: 'ok' } })
    }
    return Promise.reject(new Error(`unexpected ${url}`))
  })
  get.mockResolvedValue({ data: { items: [{ id: 'ct-9', name: 'Doña Lupe', phone: '+5219531234567' }] } })
}

function renderModal(onMoreOptions = vi.fn(), onClose = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <QuickCampaignModal businessName="Taquería Pepe" onClose={onClose} onMoreOptions={onMoreOptions} />
      </QueryClientProvider>
    </MemoryRouter>,
  )
  return { onMoreOptions, onClose }
}

async function writeAndGenerate() {
  fireEvent.change(screen.getByLabelText('¿Qué quieres anunciar?'), { target: { value: '2x1 en tacos el viernes' } })
  fireEvent.click(screen.getByText('Armar mensaje'))
  await screen.findByText(/2x1 en tacos de \$40 en Taquería Pepe/)
}

const resumeCall = () => post.mock.calls.find(([u]) => u === '/campaigns/camp-1/resume')
const createCall = () => post.mock.calls.find(([u]) => u === '/campaigns')

describe('QuickCampaignModal', () => {
  beforeEach(() => vi.clearAllMocks())

  it('caso 1: one field "¿Qué quieres anunciar?" and "Más opciones" opens the full form', () => {
    mockApi()
    const { onMoreOptions } = renderModal()
    expect(screen.getByLabelText('¿Qué quieres anunciar?')).toBeDefined()
    fireEvent.click(screen.getByText(/Más opciones/))
    expect(onMoreOptions).toHaveBeenCalled()
  })

  it('caso 2: the AI builds the message (preview as the customer sees it) and "Otra versión" changes it', async () => {
    mockApi()
    renderModal()
    await writeAndGenerate()
    expect(screen.getByText(/Hola María López, 2x1/)).toBeDefined()
    expect(post.mock.calls[0][1]).toMatchObject({ campaign_type: 'promo', business_name: 'Taquería Pepe', intent: '2x1 en tacos el viernes' })
    fireEvent.click(screen.getByText('Otra versión'))
    await waitFor(() => expect((screen.getByLabelText('Texto del mensaje') as HTMLTextAreaElement).value).toBe('Versión dos'))
  })

  it('caso 7 y 8: without WhatsApp shows who hears it and who sees it in their chat, only the web button and "Conecta tu chip"', async () => {
    mockApi()
    renderModal()
    await writeAndGenerate()
    expect(await screen.findByText(/A 1 cliente les suena aviso · 3 clientes la ven en su chat cuando entren/)).toBeDefined()
    expect(screen.getByText('Mandar gratis por web')).toBeDefined()
    expect(screen.queryByText(/Mandar también por WhatsApp/)).toBeNull()
    expect(screen.getByRole('link', { name: 'Conecta tu chip' }).getAttribute('href')).toBe('/app/settings')
  })

  it('caso 9: with WhatsApp connected also offers WhatsApp with its approximate cost', async () => {
    mockApi({ whatsapp_connected: true, whatsapp: 5, whatsapp_cost_mxn: 3.67 })
    renderModal()
    await writeAndGenerate()
    expect(await screen.findByText(/Mandar también por WhatsApp \(aprox \$3\.67\)/)).toBeDefined()
  })

  it('caso 5: "Los que compraron" with nobody turns off the button and says why', async () => {
    mockApi({ web: 0, web_chat: 0, total: 0 })
    renderModal()
    await writeAndGenerate()
    fireEvent.click(screen.getByText('Los que compraron'))
    expect(await screen.findByText(/Nadie te ha comprado en los últimos 90 días/)).toBeDefined()
    const reachCall = post.mock.calls.filter(([u]) => u === '/campaigns/reach-preview').at(-1)
    expect(reachCall?.[1]).toEqual({ segment: { bought_days: 90 } })
    expect((screen.getByText('Mandar gratis por web').closest('button') as HTMLButtonElement).disabled).toBe(true)
  })

  it('caso 6: "Uno" searches by name or phone and sends only to that customer', async () => {
    mockApi()
    renderModal()
    await writeAndGenerate()
    fireEvent.click(screen.getByText('Uno'))
    expect(screen.getByText('Escoge a quién se la mandas.')).toBeDefined()
    fireEvent.change(screen.getByLabelText('Buscar cliente'), { target: { value: 'lupe' } })
    fireEvent.click(await screen.findByText('Doña Lupe'))
    expect(get).toHaveBeenCalledWith('/contacts', { params: { q: 'lupe', status: 'active', page_size: 8 } })
    await screen.findByText(/les suena aviso/)
    fireEvent.click(screen.getByText('Mandar gratis por web'))
    await waitFor(() => expect(resumeCall()).toBeDefined())
    expect((createCall()?.[1] as { segment: unknown }).segment).toEqual({ specific_contacts: ['ct-9'] })
  })

  it('caso 10: "Mandar gratis por web" creates it and sends it web only', async () => {
    mockApi()
    const { onClose } = renderModal()
    await writeAndGenerate()
    await screen.findByText(/les suena aviso/)
    fireEvent.click(screen.getByText('Mandar gratis por web'))
    await waitFor(() => expect(onClose).toHaveBeenCalled())
    expect(resumeCall()?.[1]).toEqual({ web_only: true })
    const body = createCall()?.[1] as { ab_test: Record<string, unknown>; segment: unknown }
    expect(body.segment).toEqual({})
    expect(body.ab_test.has_coupon).toBeUndefined() // caso 11: sin tocar descuento, no hay cupón
  })

  it('caso 11: touching 15% adds a coupon to the campaign', async () => {
    mockApi()
    renderModal()
    await writeAndGenerate()
    fireEvent.click(screen.getByText('15%'))
    expect(screen.getByText(/Cupón: 15% de descuento/)).toBeDefined()
    await screen.findByText(/les suena aviso/)
    fireEvent.click(screen.getByText('Mandar gratis por web'))
    await waitFor(() => expect(resumeCall()).toBeDefined())
    expect((createCall()?.[1] as { ab_test: unknown }).ab_test).toMatchObject({ has_coupon: true, coupon_description: '15% de descuento' })
  })

  it('caso 12: if sending fails, says why, keeps the text and the draft; retry reuses the draft', async () => {
    mockApi({}, { resumeFails: true })
    const { onClose } = renderModal()
    await writeAndGenerate()
    await screen.findByText(/les suena aviso/)
    fireEvent.click(screen.getByText('Mandar gratis por web'))
    expect(await screen.findByRole('alert')).toBeDefined()
    expect(screen.getByRole('alert').textContent).toMatch(/hace poco\. La promo quedó guardada como borrador\./)
    expect(onClose).not.toHaveBeenCalled()
    expect((screen.getByLabelText('Texto del mensaje') as HTMLTextAreaElement).value).toMatch(/2x1 en tacos de \$40/)
    patch.mockResolvedValue({ data: {} })
    fireEvent.click(screen.getByText('Mandar gratis por web'))
    await waitFor(() => expect(patch).toHaveBeenCalledWith('/campaigns/camp-1', expect.anything()))
    expect(post.mock.calls.filter(([u]) => u === '/campaigns')).toHaveLength(1)
  })
})

describe('quickCampaign helpers', () => {
  it('names the campaign from what the owner asked, short', () => {
    expect(campaignName('  2x1   en tacos ')).toBe('2x1 en tacos')
    expect(campaignName('a'.repeat(80)).length).toBe(58)
  })

  it('reach line counts those who already rang today as "in their chat"', () => {
    expect(webReachLine({ ...REACH, web: 2, web_silent: 1, web_chat: 0 })).toBe('A 1 cliente les suena aviso · 1 cliente la ven en su chat cuando entren')
  })

  it('without discount the body has no coupon', () => {
    expect(buildCampaignBody('x', 'y', 'all', null, 0).ab_test).toEqual({ enabled: false, campaign_mode: 'regular' })
  })
})
