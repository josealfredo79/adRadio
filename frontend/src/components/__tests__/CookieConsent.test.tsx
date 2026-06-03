import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, beforeEach } from 'vitest'
import CookieConsent from '../CookieConsent'

describe('CookieConsent', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('renders both buttons when no consent stored', () => {
    render(<CookieConsent />)
    expect(screen.getByText('Solo necesarias')).toBeInTheDocument()
    expect(screen.getByText('Aceptar todas')).toBeInTheDocument()
  })

  it('hides after accepting all', () => {
    render(<CookieConsent />)
    fireEvent.click(screen.getByText('Aceptar todas'))
    expect(screen.queryByText('Solo necesarias')).not.toBeInTheDocument()
    expect(localStorage.getItem('cookie_consent')).toBe('all')
  })

  it('hides after accepting necessary only', () => {
    render(<CookieConsent />)
    fireEvent.click(screen.getByText('Solo necesarias'))
    expect(screen.queryByText('Aceptar todas')).not.toBeInTheDocument()
    expect(localStorage.getItem('cookie_consent')).toBe('necessary')
  })

  it('does not render if consent already stored', () => {
    localStorage.setItem('cookie_consent', 'all')
    render(<CookieConsent />)
    expect(screen.queryByText('Solo necesarias')).not.toBeInTheDocument()
  })
})
