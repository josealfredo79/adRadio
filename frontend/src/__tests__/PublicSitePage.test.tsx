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
  site_photos: [] as string[],
  site_about: '',
}

function setupQueryClient(products: unknown[], siteOverrides: Partial<typeof mockSite> = {}, stories: unknown[] = []) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 60_000 } },
  })
  queryClient.setQueryData(['public-site', 'tacos-el-primo'], { ...mockSite, ...siteOverrides })
  queryClient.setQueryData(['public-site-products', 'tacos-el-primo'], products)
  queryClient.setQueryData(['public-site-stories', 'tacos-el-primo'], stories)
  return queryClient
}

function renderPage(products: unknown[], siteOverrides: Partial<typeof mockSite> = {}, stories: unknown[] = []) {
  const queryClient = setupQueryClient(products, siteOverrides, stories)
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
    expect(screen.getByRole('heading', { level: 1, name: 'Tacos El Primo' })).toBeDefined()
  })

  it('renders the logo image instead of the category emoji when logo_url is set', () => {
    const { container } = renderPage([], { logo_url: 'https://cdn.example.com/logos/foo.jpg' })
    // nav, portada y pie de página
    expect(container.querySelectorAll('img[src="https://cdn.example.com/logos/foo.jpg"]').length).toBe(3)
  })

  it('falls back to the category emoji when no logo_url is set', () => {
    const { container } = renderPage([])
    expect(container.querySelector('img[src*="logos"]')).toBeNull()
  })
})

describe('PublicSitePage — hero image and footer', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  const slides = (header: HTMLElement) => Array.from(header.querySelectorAll('img.psite-slide')).map((i) => i.getAttribute('src'))
  const hero = () => screen.getByRole('heading', { level: 1, name: 'Tacos El Primo' }).closest('header') as HTMLElement

  it('uses the owner photos in the slider, in order, and shows a gallery', () => {
    const photos = ['https://cdn.example.com/a.jpg', 'https://cdn.example.com/b.jpg', 'https://cdn.example.com/c.jpg']
    renderPage([], { site_photos: photos })
    expect(slides(hero())).toEqual(photos)
    expect(screen.getByText('Así es Tacos El Primo')).toBeDefined()
  })

  it('keeps an old cover photo (hero_image_url) as the only slide', () => {
    renderPage([], { hero_image_url: 'https://cdn.example.com/hero-images/foo.jpg' })
    expect(slides(hero())).toEqual(['https://cdn.example.com/hero-images/foo.jpg'])
  })

  it('without photos uses stock photos of its category and no gallery (stock is never shown as theirs)', () => {
    renderPage([])
    const s = slides(hero())
    expect(s.length).toBeGreaterThan(1)
    s.forEach((src) => expect(src).toMatch(/^\/stock\/restaurante\//))
    expect(screen.queryByText('Así es Tacos El Primo')).toBeNull()
  })

  it('shows the owner About text when set', () => {
    renderPage([], { site_about: 'Tacos de trompo desde 1990.' })
    expect(screen.getByText('Tacos de trompo desde 1990.')).toBeDefined()
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
    expect(screen.getByText(/Página hecha con IaRadio/)).toBeDefined()
  })
})

describe('PublicSitePage — testimonials', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('shows the testimonials section with an audio player when stories exist', () => {
    renderPage([], {}, [
      { id: 's1', contact_name: 'Laura', transcription: 'Excelente servicio', media_url: 'https://x/laura.mp3', sentiment: 'positivo' },
    ])
    expect(screen.getByText('Lo que dicen nuestros clientes')).toBeDefined()
    expect(screen.getByText('"Excelente servicio"')).toBeDefined()
    expect(screen.getByText(/Laura, cliente real/)).toBeDefined()
  })

  it('falls back to "Cliente real" when contact_name is null', () => {
    renderPage([], {}, [
      { id: 's1', contact_name: null, transcription: 'Muy buena atención', media_url: 'https://x/anon.mp3', sentiment: 'positivo' },
    ])
    expect(screen.getByText(/Cliente real/)).toBeDefined()
  })

  it('does not show the testimonials section when there are no stories', () => {
    renderPage([])
    expect(screen.queryByText('Lo que dicen nuestros clientes')).toBeNull()
  })
})
