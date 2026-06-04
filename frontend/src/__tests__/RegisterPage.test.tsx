import { render, screen } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { HelmetProvider } from 'react-helmet-async'
import { describe, it, expect, vi } from 'vitest'
import RegisterPage from '@/pages/RegisterPage'

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ register: vi.fn(), user: null, loading: false }),
}))

function Wrapper({ children }: { children: React.ReactNode }) {
  return (
    <HelmetProvider>
      <BrowserRouter>{children}</BrowserRouter>
    </HelmetProvider>
  )
}

describe('RegisterPage', () => {
  it('renders registration form', () => {
    render(<RegisterPage />, { wrapper: Wrapper })
    expect(screen.getByText('Crear cuenta')).toBeDefined()
    expect(screen.getByPlaceholderText('tu@negocio.com')).toBeDefined()
    expect(screen.getByPlaceholderText(/Mín. 8 caracteres/)).toBeDefined()
    expect(screen.getByPlaceholderText('Ej: Restaurante La Paloma')).toBeDefined()
    expect(screen.getByRole('button', { name: /crear cuenta gratis/i })).toBeDefined()
  })

  it('renders link to login', () => {
    render(<RegisterPage />, { wrapper: Wrapper })
    expect(screen.getByText(/Inicia sesión/i)).toBeDefined()
  })

  it('renders password requirements hint', () => {
    render(<RegisterPage />, { wrapper: Wrapper })
    expect(screen.getByPlaceholderText(/Mín. 8 caracteres/)).toBeDefined()
  })
})
