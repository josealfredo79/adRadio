import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import LearnCard from '@/components/LearnCard'

// docs/specs/2026-10-12-bot-aprende-del-inbox.md — lo que ve el dueño en el Inbox.
const post = vi.fn()
vi.mock('@/lib/api', () => ({ default: { post: (...a: unknown[]) => post(...a) } }))

const SUGGESTION = {
  question: '¿Hacen envíos?',
  answer: 'Sí, a todo Tlaxiaco por $30.',
  replaces: [] as { id: string; text: string }[],
  documents: [] as string[],
}

function respond(suggestion: unknown) {
  post.mockImplementation((url: string) =>
    url.endsWith('/learn-suggestion')
      ? Promise.resolve({ data: { suggestion } })
      : Promise.resolve({ data: { saved: true, replaced: 0 } }),
  )
}

function renderCard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <LearnCard conversationId="c1" msgId="m1" />
    </QueryClientProvider>,
  )
}

describe('LearnCard', () => {
  beforeEach(() => vi.clearAllMocks())

  it('caso 1: shows the generalized question and answer, editable', async () => {
    respond(SUGGESTION)
    renderCard()
    expect(await screen.findByText('¿Guardo esto para que el bot lo sepa?')).toBeDefined()
    expect((screen.getByLabelText('Pregunta') as HTMLTextAreaElement).value).toBe('¿Hacen envíos?')
    expect((screen.getByLabelText('Respuesta') as HTMLTextAreaElement).value).toBe('Sí, a todo Tlaxiaco por $30.')
    expect(post).toHaveBeenCalledWith('/conversations/c1/learn-suggestion', { msg_id: 'm1' })
  })

  it('caso 2 y 8: no suggestion (personal reply or AI failed) shows nothing', async () => {
    respond(null)
    const { container } = renderCard()
    await waitFor(() => expect(post).toHaveBeenCalled())
    expect(container.innerHTML).toBe('')
  })

  it('caso 8: a failing request shows nothing', async () => {
    post.mockRejectedValue(new Error('500'))
    const { container } = renderCard()
    await waitFor(() => expect(post).toHaveBeenCalled())
    expect(container.innerHTML).toBe('')
  })

  it('caso 4: Guardar sends exactly what the owner left written', async () => {
    respond(SUGGESTION)
    renderCard()
    fireEvent.change(await screen.findByLabelText('Respuesta'), { target: { value: 'Sí, $35 a todo Tlaxiaco.' } })
    fireEvent.click(screen.getByText('Guardar'))
    expect(await screen.findByText(/el bot ya lo sabe/)).toBeDefined()
    expect(post).toHaveBeenCalledWith('/conversations/c1/learn', {
      question: '¿Hacen envíos?',
      answer: 'Sí, $35 a todo Tlaxiaco.',
      replace_ids: [],
    })
  })

  it('caso 5: No closes the card and saves nothing', async () => {
    respond(SUGGESTION)
    const { container } = renderCard()
    fireEvent.click(await screen.findByText('No'))
    expect(container.innerHTML).toBe('')
    expect(post).toHaveBeenCalledTimes(1)
  })

  it('caso 6: shows what the bot used to say and replaces it on save', async () => {
    respond({ ...SUGGESTION, replaces: [{ id: 'kb1', text: 'Pregunta: ¿Envían?\nRespuesta: Sí, $25.' }] })
    renderCard()
    expect(await screen.findByText('Sí, $25.')).toBeDefined()
    fireEvent.click(screen.getByText('Guardar'))
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/conversations/c1/learn', expect.objectContaining({ replace_ids: ['kb1'] })),
    )
  })

  it('caso 7: warns about a contradicting document', async () => {
    respond({ ...SUGGESTION, documents: ['menu.pdf'] })
    renderCard()
    expect(await screen.findByText(/Tu documento «menu.pdf» dice otra cosa/)).toBeDefined()
  })

  it('cannot save an empty answer', async () => {
    respond(SUGGESTION)
    renderCard()
    fireEvent.change(await screen.findByLabelText('Respuesta'), { target: { value: '  ' } })
    expect((screen.getByText('Guardar') as HTMLButtonElement).disabled).toBe(true)
  })
})
