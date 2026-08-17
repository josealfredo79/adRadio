import { render, screen } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { HelmetProvider } from 'react-helmet-async'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import PublicSitePage from '@/pages/PublicSitePage'

const mockSite = {
  advertiser_id: 'adv-1',
  business_name: 'Tacos El Primo',
  business_category: 'restaurante',
  city: 'Tlaxiaco',
  agent: 'Sofia',
  greeting: 'Hola, bienvenido',
  color: '#ff5500',
  tagline: '',
  logo_url: '',
  hero_image_url: '',
  site_theme: 'medianoche',
  whatsapp_number: '',
}

function setupQueryClient(products: unknown[], siteOverrides: Partial<typeof mockSite> = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 60_000 } },
  })
  queryClient.setQueryData(['public-site', 'tacos-el-primo'], { ...mockSite, ...siteOverrides })
  queryClient.setQueryData(['public-site-products', 'tacos-el-primo'], products)
  return queryClient
}

function renderPage(products: unknown[], siteOverrides: Partial<typeof mockSite> = {}) {
  const queryClient = setupQueryClient(products, siteOverrides)
  return render(
    <HelmetProvider>
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/sitio/tacos-el-primo']}>
          <Routes>
            <Route path="/sitio/:slug" element={<PublicSitePage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </HelmetProvider>
  )
}

describe('PublicSitePage — bestsellers section', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('shows the "más vendidos" section when at least one product has sales_count > 0', () => {
    renderPage([
      { id: 'p1', name: 'Taco al pastor', description: '', price: '25.00', category: 'Comida', photo_url: '', sales_count: 5 },
      { id: 'p2', name: 'Refresco', description: '', price: '20.00', category: 'Bebidas', photo_url: '', sales_count: 0 },
    ])
    expect(screen.getByText('🔥 Los favoritos de nuestros clientes')).toBeDefined()
    // bestseller product name appears twice: once in the bestsellers section, once in the full catalog
    expect(screen.getAllByText('Taco al pastor').length).toBe(2)
  })

  it('does not show the "más vendidos" section when every product has sales_count 0', () => {
    renderPage([
      { id: 'p1', name: 'Taco al pastor', description: '', price: '25.00', category: 'Comida', photo_url: '', sales_count: 0 },
      { id: 'p2', name: 'Refresco', description: '', price: '20.00', category: 'Bebidas', photo_url: '', sales_count: 0 },
    ])
    expect(screen.queryByText('🔥 Los favoritos de nuestros clientes')).toBeNull()
    // catalog itself still renders normally
    expect(screen.getAllByText('Taco al pastor').length).toBe(1)
  })

  it('does not show the bestsellers section when there are no products at all', () => {
    renderPage([])
    expect(screen.queryByText('🔥 Los favoritos de nuestros clientes')).toBeNull()
  })
})

describe('PublicSitePage — logo and theme', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('renders unknown/unset site_theme without crashing, falling back to the default look', () => {
    renderPage([], { site_theme: 'claro' })
    expect(screen.getByText('Tacos El Primo')).toBeDefined()
  })

  it('renders the logo image instead of the category emoji when logo_url is set', () => {
    renderPage([], { logo_url: 'https://cdn.example.com/logos/foo.jpg' })
    const img = screen.getByAltText('Tacos El Primo') as HTMLImageElement
    expect(img.src).toBe('https://cdn.example.com/logos/foo.jpg')
  })

  it('falls back to the category emoji when no logo_url is set', () => {
    renderPage([])
    expect(screen.queryByAltText('Tacos El Primo')).toBeNull()
  })
})

describe('PublicSitePage — hero image and footer', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('renders the hero image as the header background when hero_image_url is set', () => {
    renderPage([], { hero_image_url: 'https://cdn.example.com/hero-images/foo.jpg' })
    const header = screen.getByText('Tacos El Primo').closest('header') as HTMLElement
    expect(header.style.backgroundImage).toContain('https://cdn.example.com/hero-images/foo.jpg')
  })

  it('falls back to the plain gradient header when no hero_image_url is set', () => {
    renderPage([])
    const header = screen.getByText('Tacos El Primo').closest('header') as HTMLElement
    expect(header.style.background).toContain('linear-gradient')
    expect(header.style.backgroundImage).not.toContain('cdn.example.com')
  })

  it('shows a WhatsApp contact link in the footer when whatsapp_number is set', () => {
    renderPage([], { whatsapp_number: '+52 1 443 786 4292' })
    const link = screen.getByText('+52 1 443 786 4292').closest('a') as HTMLAnchorElement
    expect(link.href).toBe('https://wa.me/5214437864292')
  })

  it('hides the WhatsApp contact link when whatsapp_number is empty (not connected)', () => {
    renderPage([])
    expect(screen.queryByText(/wa.me/)).toBeNull()
  })

  it('always shows the copyright line in the footer', () => {
    renderPage([])
    expect(screen.getByText(/Todos los derechos reservados/)).toBeDefined()
  })
})
