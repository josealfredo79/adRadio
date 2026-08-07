import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import api, { getApiError } from '@/lib/api'
import { FlaskConical, Loader2, AlertTriangle, CheckCircle2, ChevronDown, ChevronRight } from 'lucide-react'
import SEO from '@/components/SEO'

interface Finding {
  type: string
  severity: string
  evidence: string
  suggestion: string
}

interface TranscriptMessage {
  role: 'user' | 'assistant'
  content: string
}

interface LabConversation {
  id: string
  persona_key: string
  persona_label: string
  transcript: TranscriptMessage[]
  score: number | null
  findings: Finding[]
}

interface LabRun {
  id: string
  status: 'running' | 'completed' | 'error'
  overall_score: number | null
  error_message: string | null
  created_at: string
  completed_at: string | null
}

interface LabRunDetail extends LabRun {
  conversations: LabConversation[]
}

const SEVERITY_STYLE: Record<string, string> = {
  alta: 'bg-red-100 text-red-700 border-red-200',
  media: 'bg-amber-100 text-amber-700 border-amber-200',
  baja: 'bg-blue-100 text-blue-700 border-blue-200',
}

const TYPE_LABEL: Record<string, string> = {
  alucinacion: 'Alucinación',
  hueco_conocimiento: 'Hueco de conocimiento',
  fallo_escalado: 'Fallo de escalado',
  tono: 'Tono',
  otro: 'Otro',
}

// Qué pone a prueba cada persona — mirrors app/services/lab/personas.py::Persona.goal.
// Vive aquí (no en la API) porque las 6 personas son un set fijo; mostrarlo hace
// evidente, sin narración, qué está probando cada conversación al hacer una demo en vivo.
const PERSONA_GOALS: Record<string, string> = {
  comprador_decidido: 'Prueba si el bot puede tomar un pedido o agendar una cita sin trabarse.',
  pregunton_precios: 'Prueba si el bot solo da precios reales de tu negocio, sin inventar.',
  cliente_enojado: 'Prueba el tono/empatía del bot y si escala a un humano cuando corresponde.',
  pregunta_lo_que_no_sabes: 'Prueba si el bot admite no saber algo en vez de inventar una respuesta.',
  exige_humano: 'Prueba si el bot cede el control a una persona cuando el cliente lo pide.',
  informal_typos: 'Prueba si el bot entiende mensajes informales, con errores y jerga mexicana.',
}

function scoreColor(score: number | null): string {
  if (score === null) return 'text-muted-foreground'
  if (score >= 80) return 'text-green-600'
  if (score >= 50) return 'text-amber-600'
  return 'text-red-600'
}

function verdict(score: number | null): { label: string; color: string } {
  if (score === null) return { label: '', color: '' }
  if (score >= 80) return { label: 'Listo para hablar con clientes reales', color: 'text-green-600' }
  if (score >= 50) return { label: 'Funciona, pero conviene revisar los hallazgos antes de confiar en él del todo', color: 'text-amber-600' }
  return { label: 'Necesita ajustes antes de atender clientes reales', color: 'text-red-600' }
}

function PersonaCard({ conv }: { conv: LabConversation }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="rounded-xl bg-card border border-border overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between p-4 hover:bg-muted transition-colors"
      >
        <div className="flex items-center gap-3 text-left">
          {open ? <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" /> : <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />}
          <div>
            <p className="text-sm font-medium text-foreground">{conv.persona_label}</p>
            {PERSONA_GOALS[conv.persona_key] && (
              <p className="text-xs text-muted-foreground mt-0.5">{PERSONA_GOALS[conv.persona_key]}</p>
            )}
          </div>
        </div>
        <span className={`shrink-0 text-lg font-bold ${scoreColor(conv.score)}`}>{conv.score ?? '—'}</span>
      </button>
      {open && (
        <div className="border-t border-border p-4 space-y-4">
          {conv.findings.length === 0 ? (
            <p className="text-sm text-green-600 flex items-center gap-1.5">
              <CheckCircle2 className="h-4 w-4" /> Sin hallazgos
            </p>
          ) : (
            <div className="space-y-2">
              {conv.findings.map((f, i) => (
                <div key={i} className={`rounded-lg border px-3 py-2 text-xs ${SEVERITY_STYLE[f.severity] || SEVERITY_STYLE.media}`}>
                  <div className="font-semibold mb-1">{TYPE_LABEL[f.type] || f.type} · {f.severity}</div>
                  <div className="mb-1">"{f.evidence}"</div>
                  <div className="italic">Sugerencia: {f.suggestion}</div>
                </div>
              ))}
            </div>
          )}
          <div className="space-y-1.5 max-h-64 overflow-y-auto rounded-lg bg-muted/50 p-3">
            {conv.transcript.length === 0 && (
              <p className="text-xs text-muted-foreground">La persona no llegó a escribir ningún mensaje.</p>
            )}
            {conv.transcript.map((m, i) => (
              <div key={i} className={`text-xs ${m.role === 'user' ? 'text-foreground' : 'text-brand-600'}`}>
                <span className="font-semibold">{m.role === 'user' ? 'Cliente: ' : 'Bot: '}</span>
                {m.content}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default function LabPage() {
  const qc = useQueryClient()
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)

  const { data: runs } = useQuery<LabRun[]>({
    queryKey: ['lab-runs'],
    queryFn: () => api.get('/lab/runs').then((r) => r.data),
  })

  const isRunning = runs?.some((r) => r.status === 'running') ?? false

  const { data: activeRun } = useQuery<LabRunDetail>({
    queryKey: ['lab-run', selectedRunId],
    queryFn: () => api.get(`/lab/runs/${selectedRunId}`).then((r) => r.data),
    enabled: !!selectedRunId,
    refetchInterval: (query) => (query.state.data?.status === 'running' ? 3000 : false),
  })

  const startMutation = useMutation({
    mutationFn: () => api.post('/lab/run').then((r) => r.data as { id: string }),
    onSuccess: (data) => {
      setSelectedRunId(data.id)
      qc.invalidateQueries({ queryKey: ['lab-runs'] })
    },
  })

  return (
    <>
      <SEO title="Laboratorio" description="El bot se prueba solo antes de hablar con clientes reales." noIndex />
      <div className="space-y-6 max-w-4xl">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="rounded-xl bg-brand-50 p-2.5">
              <FlaskConical className="h-5 w-5 text-brand-500" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-foreground">Laboratorio</h1>
              <p className="text-sm text-muted-foreground">
                Reta a tu bot con 6 tipos de clientes difíciles antes de que lo hagan tus clientes reales — nunca se envía un WhatsApp real.
              </p>
            </div>
          </div>
          <button
            onClick={() => startMutation.mutate()}
            disabled={startMutation.isPending || isRunning}
            className="flex items-center gap-2 rounded-lg bg-brand-500 px-4 py-2.5 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {(startMutation.isPending || isRunning) && <Loader2 className="h-4 w-4 animate-spin" />}
            {isRunning ? 'Corriendo…' : 'Correr Laboratorio'}
          </button>
        </div>

        {startMutation.isError && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            {getApiError(startMutation.error, 'No se pudo iniciar el Laboratorio')}
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* History */}
          <div className="lg:col-span-1 space-y-2">
            <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">Corridas recientes</h2>
            {(!runs || runs.length === 0) && (
              <p className="text-sm text-muted-foreground">Todavía no has corrido el Laboratorio.</p>
            )}
            {runs?.map((run) => (
              <button
                key={run.id}
                onClick={() => setSelectedRunId(run.id)}
                className={`w-full text-left rounded-lg border px-3 py-2.5 transition-colors ${
                  selectedRunId === run.id ? 'border-brand-500 bg-brand-50' : 'border-border bg-card hover:bg-muted'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs text-muted-foreground">
                    {new Date(run.created_at).toLocaleString('es-MX', { dateStyle: 'short', timeStyle: 'short' })}
                  </span>
                  {run.status === 'running' ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin text-brand-500" />
                  ) : run.status === 'error' ? (
                    <AlertTriangle className="h-3.5 w-3.5 text-red-500" />
                  ) : (
                    <span className={`text-sm font-bold ${scoreColor(run.overall_score)}`}>{run.overall_score}</span>
                  )}
                </div>
              </button>
            ))}
          </div>

          {/* Detail */}
          <div className="lg:col-span-2 space-y-4">
            {!selectedRunId && (
              <div className="rounded-xl border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
                Corre el Laboratorio o selecciona una corrida anterior para ver los resultados.
              </div>
            )}
            {activeRun?.status === 'error' && (
              <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                Error al correr el Laboratorio: {activeRun.error_message}
              </div>
            )}
            {activeRun?.status === 'running' && (
              <div className="rounded-xl border border-border bg-card p-6 flex items-center gap-3">
                <Loader2 className="h-5 w-5 animate-spin text-brand-500" />
                <span className="text-sm text-muted-foreground">
                  Corriendo las 6 personas contra tu bot… esto puede tardar varios minutos.
                </span>
              </div>
            )}
            {activeRun?.status === 'completed' && (
              <>
                <div className="rounded-xl border border-border bg-card p-6 flex items-center gap-4">
                  <span className={`text-4xl font-bold ${scoreColor(activeRun.overall_score)}`}>
                    {activeRun.overall_score}
                  </span>
                  <div>
                    <p className="text-sm font-medium text-foreground">Score general</p>
                    <p className={`text-xs font-medium mt-0.5 ${verdict(activeRun.overall_score).color}`}>
                      {verdict(activeRun.overall_score).label}
                    </p>
                  </div>
                </div>
                <div className="space-y-3">
                  {activeRun.conversations.map((conv) => (
                    <PersonaCard key={conv.id} conv={conv} />
                  ))}
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </>
  )
}
