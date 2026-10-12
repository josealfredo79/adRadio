import { useEffect, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Lightbulb, X } from 'lucide-react'
import api from '@/lib/api'

interface Suggestion {
  question: string
  answer: string
  replaces: { id: string; text: string }[]
  documents: string[]
}

// Lo que el bot ya sabía, sin el formato interno "Pregunta: … Respuesta: …".
function oldAnswer(text: string): string {
  const m = text.match(/Respuesta:\s*([\s\S]*)$/)
  return (m ? m[1] : text).trim()
}

/**
 * Después de contestar desde el Inbox: si lo que el dueño dijo sirve para
 * todos los clientes, se le ofrece guardarlo para que el bot lo sepa
 * (docs/specs/2026-10-12-bot-aprende-del-inbox.md). Si no sirve o la IA
 * falla, no se muestra nada.
 */
export default function LearnCard({ conversationId, msgId }: { conversationId: string; msgId: string }) {
  const [closed, setClosed] = useState(false)
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState('')

  const { data: suggestion } = useQuery({
    queryKey: ['learn-suggestion', msgId],
    queryFn: () =>
      api
        .post(`/conversations/${conversationId}/learn-suggestion`, { msg_id: msgId })
        .then((r) => r.data.suggestion as Suggestion | null),
    staleTime: Infinity,
    retry: false,
  })

  useEffect(() => {
    if (suggestion) {
      setQuestion(suggestion.question)
      setAnswer(suggestion.answer)
    }
  }, [suggestion])

  const save = useMutation({
    mutationFn: () =>
      api.post(`/conversations/${conversationId}/learn`, {
        question: question.trim(),
        answer: answer.trim(),
        replace_ids: suggestion?.replaces.map((r) => r.id) ?? [],
      }),
  })

  if (!suggestion || closed) return null

  if (save.isSuccess) {
    return (
      <div className="mx-4 mb-2 flex items-center justify-between rounded-xl bg-emerald-50 px-3 py-2 text-xs text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300">
        <span>✓ Listo, el bot ya lo sabe. Puedes verlo en Base de conocimiento → respuestas del dueño.</span>
        <button onClick={() => setClosed(true)} aria-label="Cerrar" className="ml-2 shrink-0">
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
    )
  }

  const field =
    'w-full resize-none rounded-lg border border-amber-200 bg-white px-2 py-1.5 text-sm text-gray-800 focus:border-amber-400 focus:outline-none dark:border-amber-800 dark:bg-gray-900 dark:text-gray-200'

  return (
    <div className="mx-4 mb-2 rounded-xl border border-amber-200 bg-amber-50 p-3 dark:border-amber-800 dark:bg-amber-950/30">
      <p className="mb-2 flex items-center gap-1.5 text-sm font-medium text-amber-900 dark:text-amber-200">
        <Lightbulb className="h-4 w-4" />
        ¿Guardo esto para que el bot lo sepa?
      </p>
      <label className="mb-1 block text-[11px] text-amber-800 dark:text-amber-300">Si un cliente pregunta</label>
      <textarea aria-label="Pregunta" rows={1} value={question} onChange={(e) => setQuestion(e.target.value)} className={field} />
      <label className="mb-1 mt-2 block text-[11px] text-amber-800 dark:text-amber-300">El bot contesta</label>
      <textarea aria-label="Respuesta" rows={2} value={answer} onChange={(e) => setAnswer(e.target.value)} className={field} />

      {suggestion.replaces.map((r) => (
        <p key={r.id} className="mt-2 text-xs text-amber-800 dark:text-amber-300">
          Antes el bot decía: <span className="line-through">{oldAnswer(r.text)}</span> — se va a reemplazar.
        </p>
      ))}
      {suggestion.documents.map((d) => (
        <p key={d} className="mt-2 text-xs text-amber-800 dark:text-amber-300">
          Tu documento «{d}» dice otra cosa — corrígelo ahí para que no se contradiga.
        </p>
      ))}

      <div className="mt-3 flex gap-2">
        <button
          onClick={() => save.mutate()}
          disabled={!question.trim() || !answer.trim() || save.isPending}
          className="rounded-lg bg-amber-500 px-4 py-1.5 text-sm font-medium text-white hover:bg-amber-600 disabled:opacity-40"
        >
          {save.isPending ? 'Guardando…' : 'Guardar'}
        </button>
        <button
          onClick={() => setClosed(true)}
          className="rounded-lg px-4 py-1.5 text-sm text-amber-800 hover:bg-amber-100 dark:text-amber-300 dark:hover:bg-amber-900/40"
        >
          No
        </button>
      </div>
      {save.isError && <p className="mt-1 text-xs text-red-500">No se pudo guardar. Intenta de nuevo.</p>}
    </div>
  )
}
