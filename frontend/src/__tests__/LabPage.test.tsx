import { render, screen, fireEvent } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { HelmetProvider } from 'react-helmet-async'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect } from 'vitest'
import LabPage from '@/pages/LabPage'

function setupQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 60_000 } },
  })
}

function renderPage(queryClient: QueryClient) {
  return render(
    <HelmetProvider>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter><LabPage /></BrowserRouter>
      </QueryClientProvider>
    </HelmetProvider>
  )
}

describe('LabPage', () => {
  it('shows empty state when there are no runs yet', () => {
    const queryClient = setupQueryClient()
    queryClient.setQueryData(['lab-runs'], [])
    renderPage(queryClient)
    expect(screen.getByText(/todavía no has corrido el laboratorio/i)).toBeInTheDocument()
  })

  it('lists past runs with their score', () => {
    const queryClient = setupQueryClient()
    queryClient.setQueryData(['lab-runs'], [
      { id: 'run-1', status: 'completed', overall_score: 82, error_message: null, created_at: '2026-07-28T10:00:00Z', completed_at: '2026-07-28T10:05:00Z' },
    ])
    renderPage(queryClient)
    expect(screen.getByText('82')).toBeInTheDocument()
  })

  it('shows overall score and persona cards when a run is selected', () => {
    const queryClient = setupQueryClient()
    queryClient.setQueryData(['lab-runs'], [
      { id: 'run-1', status: 'completed', overall_score: 75, error_message: null, created_at: '2026-07-28T10:00:00Z', completed_at: '2026-07-28T10:05:00Z' },
    ])
    queryClient.setQueryData(['lab-run', 'run-1'], {
      id: 'run-1', status: 'completed', overall_score: 75, error_message: null,
      created_at: '2026-07-28T10:00:00Z', completed_at: '2026-07-28T10:05:00Z',
      conversations: [
        {
          id: 'conv-1', persona_key: 'comprador_decidido', persona_label: 'El comprador decidido',
          transcript: [{ role: 'user', content: 'Hola quiero comprar' }, { role: 'assistant', content: '¡Claro!' }],
          score: 90,
          findings: [],
        },
        {
          id: 'conv-2', persona_key: 'pregunton_precios', persona_label: 'El preguntón de precios',
          transcript: [], score: 60,
          findings: [{ type: 'alucinacion', severity: 'alta', evidence: 'precio inventado', suggestion: 'usar solo el KB' }],
        },
      ],
    })
    renderPage(queryClient)

    fireEvent.click(screen.getByText('75').closest('button')!)

    expect(screen.getByText('Score general')).toBeInTheDocument()
    expect(screen.getByText('El comprador decidido')).toBeInTheDocument()
    expect(screen.getByText('El preguntón de precios')).toBeInTheDocument()
  })

  it('disables the run button while a run is already in progress', () => {
    const queryClient = setupQueryClient()
    queryClient.setQueryData(['lab-runs'], [
      { id: 'run-1', status: 'running', overall_score: null, error_message: null, created_at: '2026-07-28T10:00:00Z', completed_at: null },
    ])
    renderPage(queryClient)
    const button = screen.getByRole('button', { name: /corriendo/i })
    expect(button).toBeDisabled()
  })
})
