import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { BrowserRouter } from 'react-router-dom'
import { HelmetProvider } from 'react-helmet-async'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import KnowledgeBasePage from '@/pages/KnowledgeBasePage'

const mockFiles = [
  { id: '1', filename: 'menu.pdf', file_type: 'pdf', version: 1, processing_status: 'done' as const, created_at: '2025-01-01T00:00:00Z' },
  { id: '2', filename: 'catalogo.docx', file_type: 'docx', version: 2, processing_status: 'processing' as const, created_at: '2025-01-02T00:00:00Z' },
  { id: '3', filename: 'data.xlsx', file_type: 'xlsx', version: 1, processing_status: 'error' as const, created_at: '2025-01-03T00:00:00Z' },
]

function setupQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 60_000 } },
  })
}

function renderPage(clients?: { queryClient?: QueryClient }) {
  const queryClient = clients?.queryClient ?? setupQueryClient()
  queryClient.setQueryData(['knowledge-base'], mockFiles)
  return {
    queryClient,
    ...render(
      <HelmetProvider>
        <QueryClientProvider client={queryClient}>
          <BrowserRouter><KnowledgeBasePage /></BrowserRouter>
        </QueryClientProvider>
      </HelmetProvider>
    ),
  }
}

describe('KnowledgeBasePage', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('renders page title and description', () => {
    renderPage()
    expect(screen.getByText('Base de conocimiento')).toBeDefined()
    expect(screen.getByText(/Sube documentos/)).toBeDefined()
  })

  it('renders supported formats info box', () => {
    renderPage()
    expect(screen.getByText(/Formatos soportados/)).toBeDefined()
    expect(screen.getByText(/Word/)).toBeDefined()
  })

  it('renders upload button', () => {
    renderPage()
    expect(screen.getByText('Subir documento')).toBeDefined()
  })

  it('renders file list with filenames', () => {
    renderPage()
    expect(screen.getByText('menu.pdf')).toBeDefined()
    expect(screen.getByText('catalogo.docx')).toBeDefined()
    expect(screen.getByText('data.xlsx')).toBeDefined()
  })

  it('shows processing status badges', () => {
    renderPage()
    expect(screen.getByText('Procesado')).toBeDefined()
    expect(screen.getByText('Procesando…')).toBeDefined()
    expect(screen.getByText('Error')).toBeDefined()
  })

  it('renders SEO component', () => {
    renderPage()
    expect(screen.getByText('Base de conocimiento')).toBeDefined()
  })

  it('shows empty state when no files', () => {
    const qc = setupQueryClient()
    qc.setQueryData(['knowledge-base'], [])
    render(
      <HelmetProvider>
        <QueryClientProvider client={qc}>
          <BrowserRouter><KnowledgeBasePage /></BrowserRouter>
        </QueryClientProvider>
      </HelmetProvider>
    )
    expect(screen.getByText('No hay documentos todavía')).toBeDefined()
  })

  it('shows loading skeleton while fetching', () => {
    const qc = setupQueryClient()
    render(
      <HelmetProvider>
        <QueryClientProvider client={qc}>
          <BrowserRouter><KnowledgeBasePage /></BrowserRouter>
        </QueryClientProvider>
      </HelmetProvider>
    )
    const skeletons = document.querySelectorAll('.animate-pulse')
    expect(skeletons.length).toBe(3)
  })
})
