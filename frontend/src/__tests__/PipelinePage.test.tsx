import { render, screen } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { HelmetProvider } from 'react-helmet-async'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect } from 'vitest'
import PipelinePage from '@/pages/PipelinePage'

function setupQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 60_000 } } })
}

function renderPage(qc: QueryClient) {
  return render(
    <HelmetProvider>
      <QueryClientProvider client={qc}>
        <BrowserRouter><PipelinePage /></BrowserRouter>
      </QueryClientProvider>
    </HelmetProvider>
  )
}

const CONTACTS = [
  { id: 'c1', name: 'Juan Pérez', phone: '+521111111111', tags: ['vip'], engagement_score: 80, pipeline_stage: 'nuevo' },
  { id: 'c2', name: 'Ana López', phone: '+521222222222', tags: [], engagement_score: 20, pipeline_stage: 'cliente' },
]

describe('PipelinePage', () => {
  it('renders all 5 stage columns', () => {
    const qc = setupQueryClient()
    qc.setQueryData(['contacts-pipeline'], [])
    renderPage(qc)
    expect(screen.getByText('Nuevo')).toBeInTheDocument()
    expect(screen.getByText('En conversación')).toBeInTheDocument()
    expect(screen.getByText('Interesado')).toBeInTheDocument()
    expect(screen.getByText('Cliente')).toBeInTheDocument()
    expect(screen.getByText('Perdido')).toBeInTheDocument()
  })

  it('groups contacts into their stage column', () => {
    const qc = setupQueryClient()
    qc.setQueryData(['contacts-pipeline'], CONTACTS)
    renderPage(qc)
    expect(screen.getByText('Juan Pérez')).toBeInTheDocument()
    expect(screen.getByText('Ana López')).toBeInTheDocument()
  })

  it('shows an empty-state message for columns with no contacts', () => {
    const qc = setupQueryClient()
    qc.setQueryData(['contacts-pipeline'], CONTACTS)
    renderPage(qc)
    // "conversacion", "interesado", "perdido" are empty given CONTACTS above
    expect(screen.getAllByText('Sin contactos').length).toBe(3)
  })

  it('shows contact tags', () => {
    const qc = setupQueryClient()
    qc.setQueryData(['contacts-pipeline'], CONTACTS)
    renderPage(qc)
    expect(screen.getByText('vip')).toBeInTheDocument()
  })
})
