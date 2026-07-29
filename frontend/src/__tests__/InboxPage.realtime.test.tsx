import { render, waitFor } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { HelmetProvider } from 'react-helmet-async'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import InboxPage from '@/pages/InboxPage'
import { setAccessToken } from '@/lib/api'

class FakeEventSource {
  static instances: FakeEventSource[] = []
  url: string
  onmessage: ((event: { data: string }) => void) | null = null
  closed = false

  constructor(url: string) {
    this.url = url
    FakeEventSource.instances.push(this)
  }
  close() {
    this.closed = true
  }
}

function setupQueryClient() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 60_000 } } })
  qc.setQueryData(['conversations', 'active', false], [])
  return qc
}

function renderPage(qc: QueryClient) {
  return render(
    <HelmetProvider>
      <QueryClientProvider client={qc}>
        <BrowserRouter><InboxPage /></BrowserRouter>
      </QueryClientProvider>
    </HelmetProvider>
  )
}

describe('InboxPage real-time (SSE)', () => {
  beforeEach(() => {
    FakeEventSource.instances = []
    // @ts-expect-error jsdom has no native EventSource
    global.EventSource = FakeEventSource
    setAccessToken('fake-access-token')
  })

  afterEach(() => {
    setAccessToken(null)
  })

  it('does not open a connection without an access token', () => {
    setAccessToken(null)
    const qc = setupQueryClient()
    renderPage(qc)
    expect(FakeEventSource.instances).toHaveLength(0)
  })

  it('opens an EventSource with the token as a query param', () => {
    const qc = setupQueryClient()
    renderPage(qc)
    expect(FakeEventSource.instances).toHaveLength(1)
    expect(FakeEventSource.instances[0].url).toContain('/api/v1/conversations/events?token=fake-access-token')
  })

  it('invalidates the conversations query when a message event arrives', async () => {
    const qc = setupQueryClient()
    const invalidateSpy = vi.spyOn(qc, 'invalidateQueries')
    renderPage(qc)

    const source = FakeEventSource.instances[0]
    source.onmessage?.({ data: JSON.stringify({ type: 'message', contact_id: 'c1' }) })

    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['conversations'] })
    })
  })

  it('ignores malformed event payloads without crashing', () => {
    const qc = setupQueryClient()
    renderPage(qc)
    const source = FakeEventSource.instances[0]
    expect(() => source.onmessage?.({ data: 'not-json{{{' })).not.toThrow()
  })

  it('closes the connection on unmount', () => {
    const qc = setupQueryClient()
    const { unmount } = renderPage(qc)
    const source = FakeEventSource.instances[0]
    expect(source.closed).toBe(false)
    unmount()
    expect(source.closed).toBe(true)
  })
})
