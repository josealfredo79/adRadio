import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { BrowserRouter } from 'react-router-dom'
import { HelmetProvider } from 'react-helmet-async'
import { describe, it, expect, vi } from 'vitest'
import VerifyEmailPage from '@/pages/VerifyEmailPage'

function Wrapper({ children }: { children: React.ReactNode }) {
  return (
    <HelmetProvider>
      <BrowserRouter>{children}</BrowserRouter>
    </HelmetProvider>
  )
}

function renderPage(email = 'test@example.com') {
  window.history.pushState({}, '', `?email=${encodeURIComponent(email)}`)
  return render(<VerifyEmailPage />, { wrapper: Wrapper })
}

describe('VerifyEmailPage', () => {
  it('renders verify form with email', () => {
    renderPage('usuario@correo.com')
    expect(screen.getByText('Verifica tu email')).toBeDefined()
    expect(screen.getByText(/usuario@correo\.com/)).toBeDefined()
    expect(screen.getByPlaceholderText('000000')).toBeDefined()
    expect(screen.getByText('Verificar')).toBeDefined()
  })

  it('shows link back to register', () => {
    renderPage()
    expect(screen.getByText('Volver al registro')).toBeDefined()
  })

  it('disables button when code is not 6 digits', () => {
    renderPage()
    const btn = screen.getByRole('button', { name: /verificar/i })
    expect(btn).toBeDisabled()
  })

  it('enables button when code is 6 digits', async () => {
    const user = userEvent.setup()
    renderPage()
    const input = screen.getByPlaceholderText('000000')
    await user.type(input, '123456')
    const btn = screen.getByRole('button', { name: /verificar/i })
    expect(btn).not.toBeDisabled()
  })

  it('filters non-digit characters', async () => {
    const user = userEvent.setup()
    renderPage()
    const input = screen.getByPlaceholderText('000000') as HTMLInputElement
    await user.type(input, 'abc123def456')
    expect(input.value).toBe('123456')
  })

  it('shows error on failed verification', async () => {
    const user = userEvent.setup()
    renderPage()
    const input = screen.getByPlaceholderText('000000')
    await user.type(input, '999999')
    const btn = screen.getByRole('button', { name: /verificar/i })
    btn.removeAttribute('disabled')
    await user.click(btn)
    await waitFor(() => {
      expect(screen.getByText('Código inválido')).toBeDefined()
    })
  })
})
