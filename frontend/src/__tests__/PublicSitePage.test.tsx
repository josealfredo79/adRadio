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
}

function setupQueryClient(products: unknown[]) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 60_000 } },
  })
  queryClient.setQueryData(['public-site', 'tacos-el-primo'], mockSite)
  queryClient.setQueryData(['public-site-products', 'tacos-el-primo'], products)
  return queryClient
}

function renderPage(products: unknown[]) {
  const queryClient = setupQueryClient(products)
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
