import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import api, { getApiError } from '@/lib/api'
import { Kanban, Flame, Thermometer, Snowflake } from 'lucide-react'
import SEO from '@/components/SEO'

interface PipelineContact {
  id: string
  name: string
  phone: string
  tags: string[]
  engagement_score: number
  pipeline_stage: string
}

const STAGES: { key: string; label: string }[] = [
  { key: 'nuevo', label: 'Nuevo' },
  { key: 'conversacion', label: 'En conversación' },
  { key: 'interesado', label: 'Interesado' },
  { key: 'cliente', label: 'Cliente' },
  { key: 'perdido', label: 'Perdido' },
]

function engagementIcon(score: number) {
  if (score >= 70) return <Flame className="h-3.5 w-3.5 text-red-500" />
  if (score >= 30) return <Thermometer className="h-3.5 w-3.5 text-orange-400" />
  return <Snowflake className="h-3.5 w-3.5 text-blue-400" />
}

export default function PipelinePage() {
  const qc = useQueryClient()
  const [draggingId, setDraggingId] = useState<string | null>(null)
  const [dragOverStage, setDragOverStage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const { data: contacts, isLoading } = useQuery<PipelineContact[]>({
    queryKey: ['contacts-pipeline'],
    queryFn: () => api.get('/contacts/pipeline').then((r) => r.data),
  })

  const byStage = useMemo(() => {
    const grouped: Record<string, PipelineContact[]> = {}
    for (const s of STAGES) grouped[s.key] = []
    for (const c of contacts ?? []) {
      (grouped[c.pipeline_stage] ?? grouped.nuevo).push(c)
    }
    return grouped
  }, [contacts])

  const moveMutation = useMutation({
    mutationFn: ({ id, stage }: { id: string; stage: string }) =>
      api.patch(`/contacts/${id}`, { pipeline_stage: stage }),
    onMutate: async ({ id, stage }) => {
      setError(null)
      await qc.cancelQueries({ queryKey: ['contacts-pipeline'] })
      const previous = qc.getQueryData<PipelineContact[]>(['contacts-pipeline'])
      qc.setQueryData<PipelineContact[]>(['contacts-pipeline'], (old) =>
        old?.map((c) => (c.id === id ? { ...c, pipeline_stage: stage } : c))
      )
      return { previous }
    },
    onError: (err, _vars, context) => {
      if (context?.previous) qc.setQueryData(['contacts-pipeline'], context.previous)
      setError(getApiError(err, 'No se pudo mover el contacto'))
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ['contacts-pipeline'] }),
  })

  const handleDrop = (stage: string) => {
    setDragOverStage(null)
    if (!draggingId) return
    const contact = contacts?.find((c) => c.id === draggingId)
    if (contact && contact.pipeline_stage !== stage) {
      moveMutation.mutate({ id: draggingId, stage })
    }
    setDraggingId(null)
  }

  return (
    <>
      <SEO title="Pipeline" description="Kanban de leads — de nuevo contacto a cliente." noIndex />
      <div className="space-y-6">
        <div className="flex items-center gap-3">
          <div className="rounded-xl bg-brand-50 p-2.5">
            <Kanban className="h-5 w-5 text-brand-500" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-foreground">Pipeline</h1>
            <p className="text-sm text-muted-foreground">Arrastra un contacto entre etapas para actualizar su avance.</p>
          </div>
        </div>

        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-700">{error}</div>
        )}

        {isLoading ? (
          <p className="text-sm text-muted-foreground">Cargando…</p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
            {STAGES.map((stage) => (
              <div
                key={stage.key}
                onDragOver={(e) => {
                  e.preventDefault()
                  setDragOverStage(stage.key)
                }}
                onDragLeave={() => setDragOverStage((s) => (s === stage.key ? null : s))}
                onDrop={(e) => {
                  e.preventDefault()
                  handleDrop(stage.key)
                }}
                className={`rounded-xl border p-3 min-h-[300px] space-y-2 transition-colors ${
                  dragOverStage === stage.key ? 'border-brand-500 bg-brand-50' : 'border-border bg-muted/30'
                }`}
              >
                <div className="flex items-center justify-between px-1 pb-1">
                  <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{stage.label}</h2>
                  <span className="text-xs font-medium text-muted-foreground">{byStage[stage.key]?.length ?? 0}</span>
                </div>
                {byStage[stage.key]?.map((contact) => (
                  <div
                    key={contact.id}
                    draggable
                    onDragStart={() => setDraggingId(contact.id)}
                    onDragEnd={() => setDraggingId(null)}
                    className={`rounded-lg border border-border bg-card p-3 shadow-sm cursor-grab active:cursor-grabbing transition-opacity ${
                      draggingId === contact.id ? 'opacity-40' : 'opacity-100'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm font-medium text-foreground truncate">{contact.name}</span>
                      {engagementIcon(contact.engagement_score)}
                    </div>
                    <p className="text-xs text-muted-foreground mt-0.5">{contact.phone}</p>
                    {contact.tags.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-2">
                        {contact.tags.slice(0, 3).map((t) => (
                          <span key={t} className="rounded-full bg-muted px-2 py-0.5 text-[10px] text-muted-foreground">
                            {t}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
                {byStage[stage.key]?.length === 0 && (
                  <p className="text-xs text-muted-foreground/60 text-center py-6">Sin contactos</p>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  )
}
