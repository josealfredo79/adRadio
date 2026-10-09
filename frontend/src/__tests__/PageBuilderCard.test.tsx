import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import PageBuilderCard from '@/components/PageBuilderCard'

const setUser = vi.fn()
let currentUser: Record<string, unknown> | null = null

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ user: currentUser, setUser, loading: false }),
}))

const get = vi.fn()
vi.mock('@/lib/api', () => ({ default: { get: (...a: unknown[]) => get(...a) } }))

vi.mock('@/components/AgentChat', () => ({
  default: ({ ownerOnboarding, onClose }: { ownerOnboarding?: { name: string | null }; onClose: () => void }) => (
    <div data-testid="chat">
      <span>owner:{ownerOnboarding?.name}</span>
      <button onClick={onClose}>cerrar</button>
    </div>
  ),
}))

const SITE = {
  advertiser_id: 'a1',
  business_name: 'IaRadio',
  agent: 'IaRadio',
  color: '#25D366',
  greeting: 'Hola',
  site_theme: 'medianoche',
}

function renderCard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <PageBuilderCard />
    </QueryClientProvider>,
  )
}

describe('PageBuilderCard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    currentUser = { role: 'advertiser', slug: null, business_name: 'Mi Taquería' }
    get.mockImplementation((url: string) =>
      Promise.resolve({ data: url === '/me' ? { role: 'advertiser', slug: 'mi-taqueria' } : SITE }),
    )
  })

  it('is offered to an advertiser who has no page yet', () => {
    renderCard()
    expect(screen.getByText('Arma tu página con IaRadio')).toBeDefined()
  })

  it.each([
    ['already has a page', { role: 'advertiser', slug: 'mi-taqueria' }],
    ['is an admin', { role: 'admin', slug: null }],
  ])('is hidden when the user %s', (_label, user) => {
    currentUser = user
    renderCard()
    expect(screen.queryByText('Arma tu página con IaRadio')).toBeNull()
  })

  it('opens the bot in owner mode and refreshes the user when it closes', async () => {
    renderCard()
    expect(get).not.toHaveBeenCalled()
    fireEvent.click(screen.getByText('Arma tu página con IaRadio'))
    await screen.findByTestId('chat')
    expect(screen.getByText('owner:Mi Taquería')).toBeDefined()

    fireEvent.click(screen.getByText('cerrar'))
    await waitFor(() => expect(setUser).toHaveBeenCalledWith({ role: 'advertiser', slug: 'mi-taqueria' }))
    expect(screen.queryByTestId('chat')).toBeNull()
  })
})
