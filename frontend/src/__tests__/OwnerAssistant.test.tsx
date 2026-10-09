import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import OwnerAssistant from '@/components/OwnerAssistant'
import { CopilotProvider } from '@/contexts/CopilotContext'

const post = vi.fn()
const get = vi.fn()
vi.mock('@/lib/api', () => ({
  default: { post: (...a: unknown[]) => post(...a), get: (...a: unknown[]) => get(...a) },
  getApiError: (_e: unknown, fallback: string) => fallback,
}))

const setUser = vi.fn()
let currentUser: Record<string, unknown> = { role: 'advertiser', business_name: 'Barbería Don Pepe' }
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ user: currentUser, setUser }),
}))
vi.mock('@/components/MascotSmart', () => ({ default: () => <span /> }))

const PENDING = {
  reply: 'Voy a agregar el producto. ¿Confirmas?',
  actions: [],
  pending_confirmation: { confirmation_id: 'tok-1', tool: 'create_product', summary: 'Agregar "Tinte" al catálogo a $450.' },
}

function renderAt(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <CopilotProvider>
          <OwnerAssistant />
        </CopilotProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('OwnerAssistant (bot flotante del panel)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    sessionStorage.clear()
    currentUser = { role: 'advertiser', business_name: 'Barbería Don Pepe' }
    get.mockResolvedValue({ data: { role: 'advertiser', slug: 'barberia' } })
  })

  it('shows for every role except on the Copilot page', () => {
    currentUser = { role: 'admin' }
    const { unmount } = renderAt('/app/dashboard')
    expect(screen.getByLabelText('Abrir asistente IaRadio')).toBeDefined()
    unmount()
    currentUser = { role: 'advertiser' }
    const second = renderAt('/app/copilot')
    expect(screen.queryByLabelText('Abrir asistente IaRadio')).toBeNull()
    second.unmount()
    renderAt('/app/dashboard')
    expect(screen.getByLabelText('Abrir asistente IaRadio')).toBeDefined()
  })

  it('a product photo is uploaded and goes with the next request', async () => {
    URL.createObjectURL = vi.fn(() => 'blob:preview')
    URL.revokeObjectURL = vi.fn()
    post.mockImplementation((url: string) => {
      if (url === '/copilot/photo') return Promise.resolve({ data: { url: 'https://x/api/v1/radio/audio/products/u1/a.jpg' } })
      if (url === '/copilot/voice') return Promise.resolve({ data: PENDING })
      return Promise.resolve({ data: {} })
    })
    const { container } = renderAt('/app/dashboard')
    fireEvent.click(screen.getByLabelText('Abrir asistente IaRadio'))
    const input = container.querySelector('input[type=file]') as HTMLInputElement
    fireEvent.change(input, { target: { files: [new File(['jpg'], 'tinte.jpg', { type: 'image/jpeg' })] } })
    await screen.findByText('Foto lista: dime qué producto es.')

    fireEvent.change(screen.getByLabelText('Escribe lo que necesitas'), { target: { value: 'agrega este producto, tinte a 450' } })
    fireEvent.click(screen.getByLabelText('Enviar'))
    await screen.findByText('¿Lo hago?')
    const form = post.mock.calls.find(([u]) => u === '/copilot/voice')?.[1] as FormData
    expect(form.get('text')).toBe('agrega este producto, tinte a 450')
    expect(form.get('photo_url')).toBe('https://x/api/v1/radio/audio/products/u1/a.jpg')
    expect(post).not.toHaveBeenCalledWith('/copilot/chat', expect.anything(), expect.anything())
    expect(screen.queryByText('Foto lista: dime qué producto es.')).toBeNull()
  })

  it('writes data only after the owner says "Sí, hazlo"', async () => {
    post.mockImplementation((url: string) => {
      if (url === '/copilot/chat') return Promise.resolve({ data: PENDING })
      if (url === '/copilot/confirm') {
        return Promise.resolve({
          data: { reply: 'Listo, ya está en tu catálogo.', actions: [{ tool: 'create_product', summary: 'Producto "Tinte" agregado ($450).' }], pending_confirmation: null },
        })
      }
      return Promise.resolve({ data: {} })
    })
    renderAt('/app/dashboard')
    fireEvent.click(screen.getByLabelText('Abrir asistente IaRadio'))
    expect(screen.getByText(/Hola, Barbería Don Pepe/)).toBeDefined()

    fireEvent.change(screen.getByLabelText('Escribe lo que necesitas'), { target: { value: 'agrega tinte a 450' } })
    fireEvent.click(screen.getByLabelText('Enviar'))
    await screen.findByText('Agregar "Tinte" al catálogo a $450.')
    expect(post).toHaveBeenCalledWith('/copilot/chat', { message: 'agrega tinte a 450', history: [] }, { timeout: 45000 })
    expect(post).not.toHaveBeenCalledWith('/copilot/confirm', expect.anything())

    fireEvent.click(screen.getByText('Sí, hazlo'))
    await screen.findByText('Listo, ya está en tu catálogo.')
    expect(post).toHaveBeenCalledWith('/copilot/confirm', { confirmation_id: 'tok-1', approve: true })
    expect(screen.getByText(/Producto "Tinte" agregado/)).toBeDefined()
    expect(screen.queryByText('¿Lo hago?')).toBeNull()
    await waitFor(() => expect(setUser).toHaveBeenCalledWith({ role: 'advertiser', slug: 'barberia' }))
  })

  it('"Cancelar" discards the pending change', async () => {
    post.mockImplementation((url: string) =>
      Promise.resolve({
        data: url === '/copilot/chat' ? PENDING : { reply: 'Cancelado, no cambié nada.', actions: [], pending_confirmation: null },
      }),
    )
    renderAt('/app/dashboard')
    fireEvent.click(screen.getByLabelText('Abrir asistente IaRadio'))
    fireEvent.click(screen.getByText('Agregar un producto'))
    await screen.findByText('¿Lo hago?')
    fireEvent.click(screen.getByText('Cancelar'))
    await screen.findByText('Cancelado, no cambié nada.')
    expect(post).toHaveBeenCalledWith('/copilot/confirm', { confirmation_id: 'tok-1', approve: false })
    expect(get).not.toHaveBeenCalled()
  })
})
