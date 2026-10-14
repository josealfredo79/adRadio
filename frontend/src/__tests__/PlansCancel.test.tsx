import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { HelmetProvider } from 'react-helmet-async'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ToastProvider } from '@/contexts/ToastContext'
import PlansPage from '@/pages/PlansPage'

// Cancelar desde Planes (2026-10-13: el dueño lo buscó ahí y solo estaba en Configuración).

let currentUser: Record<string, unknown> | null = null
const refreshUser = vi.fn()
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ user: currentUser, loading: false, refreshUser }),
}))

const post = vi.fn()
vi.mock('@/lib/api', () => ({
  default: { get: vi.fn(() => Promise.reject(new Error('sin red en la prueba'))), post: (...a: unknown[]) => post(...a) },
  getApiError: () => 'error',
}))

function renderPlans() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <HelmetProvider>
      <QueryClientProvider client={qc}>
        <BrowserRouter><ToastProvider><PlansPage /></ToastProvider></BrowserRouter>
      </QueryClientProvider>
    </HelmetProvider>,
  )
}

const ACTIVE = {
  id: '1', email: 'a@b.c', subscription_status: 'active', current_plan: 'starter',
  cancel_at_period_end: false, plan_expires_at: '2026-11-13T18:00:00Z',
}

describe('Cancelar desde Planes', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    post.mockResolvedValue({ data: {} })
  })

  it('an active plan shows its renewal date and a cancel button', () => {
    currentUser = ACTIVE
    renderPlans()
    expect(screen.getByText('Tu suscripción: Arranque')).toBeDefined()
    expect(screen.getByText('Se renueva el 13 de noviembre.')).toBeDefined()
    expect(screen.getByText('Cancelar suscripción')).toBeDefined()
  })

  it('asks before cancelling, then cancels and refreshes the plan badge', async () => {
    currentUser = ACTIVE
    renderPlans()
    fireEvent.click(screen.getByText('Cancelar suscripción'))
    expect(post).not.toHaveBeenCalled()
    fireEvent.click(screen.getByText('Sí, cancelar'))
    await waitFor(() => expect(post).toHaveBeenCalledWith('/cancel-subscription'))
    await waitFor(() => expect(refreshUser).toHaveBeenCalled())
  })

  it('an already cancelled plan says until when it lasts, with no button', () => {
    currentUser = { ...ACTIVE, cancel_at_period_end: true }
    renderPlans()
    expect(screen.getByText(/Cancelada\. Sigues con tu plan hasta el 13 de noviembre/)).toBeDefined()
    expect(screen.queryByText('Cancelar suscripción')).toBeNull()
  })

  it('a trial has nothing to cancel', () => {
    currentUser = { ...ACTIVE, subscription_status: 'trial', current_plan: 'trial' }
    renderPlans()
    expect(screen.queryByText(/Tu suscripción/)).toBeNull()
  })
})
