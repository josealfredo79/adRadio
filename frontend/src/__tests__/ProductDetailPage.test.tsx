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
}

function renderPage(product: unknown) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 60_000 } } })
  queryClient.setQueryData(['public-site-product', 'tacos-el-primo', 'p1'], product)
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

describe('ProductDetailPage', () => {
  it('shows the product name, description, and formatted price', () => {
    renderPage(mockProduct)
    expect(screen.getByText('Taco al pastor')).toBeDefined()
    expect(screen.getByText('Con piña y cebolla')).toBeDefined()
    expect(screen.getByText('$25.00')).toBeDefined()
  })

  it('shows a WhatsApp link pre-filled with the product name', () => {
    renderPage(mockProduct)
    const link = screen.getByText('Preguntar por WhatsApp').closest('a')
    expect(link?.getAttribute('href')).toContain(encodeURIComponent('Taco al pastor'))
  })

  it('shows "Cotizar" when price is null', () => {
    renderPage({ ...mockProduct, price: null })
    expect(screen.getByText('Cotizar')).toBeDefined()
  })
})
