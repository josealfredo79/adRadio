import { render, screen } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { HelmetProvider } from 'react-helmet-async'
import { describe, it, expect, vi } from 'vitest'
import LoginPage from '@/pages/LoginPage'

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ login: vi.fn(), user: null, loading: false }),
}))

function Wrapper({ children }: { children: React.ReactNode }) {
  return (
    <HelmetProvider>
      <BrowserRouter>{children}</BrowserRouter>
    </HelmetProvider>
  )
}

describe('LoginPage', () => {
  it('renders login form', () => {
    render(<LoginPage />, { wrapper: Wrapper })
    expect(screen.getByText('Iniciar sesión')).toBeDefined()
    expect(screen.getByPlaceholderText('tu@negocio.com')).toBeDefined()
    expect(screen.getByPlaceholderText('••••••••')).toBeDefined()
    expect(screen.getByRole('button', { name: /entrar/i })).toBeDefined()
  })

  it('renders logo and branding', () => {
    render(<LoginPage />, { wrapper: Wrapper })
    expect(screen.getByText('IaRadio')).toBeDefined()
    expect(screen.getByText(/Radio Publicitaria por WhatsApp/)).toBeDefined()
  })

  it('renders link to register', () => {
    render(<LoginPage />, { wrapper: Wrapper })
    expect(screen.getByText(/Regístrate gratis/i)).toBeDefined()
  })
})
