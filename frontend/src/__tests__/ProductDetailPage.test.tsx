import { render, screen } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { HelmetProvider } from 'react-helmet-async'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect } from 'vitest'
import ProductDetailPage from '@/pages/ProductDetailPage'

const mockProduct = {
  id: 'p1',
  name: 'Taco al pastor',
  description: 'Con piña y cebolla',
  price: '25.00',
  category: 'Comida',
  photo_url: '',
  sales_count: 3,
  business_name: 'Tacos El Primo',
  slug: 'tacos-el-primo',
  whatsapp_number: '+52 1 443 786 4292',
}

function renderPage(product: unknown) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 60_000 } } })
  queryClient.setQueryData(['public-product', 'tacos-el-primo', 'p1'], product)
  return render(
    <HelmetProvider>
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/sitio/tacos-el-primo/producto/p1']}>
          <Routes>
            <Route path="/sitio/:slug/producto/:productId" element={<ProductDetailPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </HelmetProvider>
  )
}

function renderPageWithoutSlug(product: unknown) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 60_000 } } })
  queryClient.setQueryData(['public-product', 'adv-1', 'p1'], product)
  return render(
    <HelmetProvider>
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/p/adv-1/p1']}>
          <Routes>
            <Route path="/p/:advertiserId/:productId" element={<ProductDetailPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </HelmetProvider>
  )
}

describe('ProductDetailPage', () => {
  it('shows the product name, description, and formatted price', () => {
    renderPage(mockProduct)
    expect(screen.getByText('Taco al pastor')).toBeDefined()
    expect(screen.getByText('Con piña y cebolla')).toBeDefined()
    expect(screen.getByText('$25.00')).toBeDefined()
  })

  it('shows a WhatsApp link pre-filled with the product name, addressed to the connected number', () => {
    renderPage(mockProduct)
    const link = screen.getByText('Preguntar por WhatsApp').closest('a')
    expect(link?.getAttribute('href')).toContain(encodeURIComponent('Taco al pastor'))
    expect(link?.getAttribute('href')).toContain('https://wa.me/5214437864292')
  })

  it('hides the WhatsApp button when no number is connected (wa.me/?text= with no recipient is broken)', () => {
    renderPage({ ...mockProduct, whatsapp_number: '' })
    expect(screen.queryByText('Preguntar por WhatsApp')).toBeNull()
  })

  it('shows "Cotizar" when price is null', () => {
    renderPage({ ...mockProduct, price: null })
    expect(screen.getByText('Cotizar')).toBeDefined()
  })

  it('renders correctly via /p/:advertiserId/:productId when the advertiser has no published landing page', () => {
    renderPageWithoutSlug({ ...mockProduct, slug: '' })
    expect(screen.getByText('Taco al pastor')).toBeDefined()
    // no slug -> no "volver a {business_name}" link to a landing page that doesn't exist
    expect(screen.queryByText(/Volver a/)).toBeNull()
  })
})
