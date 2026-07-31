import { useEffect, useState } from 'react'
import { CalendarRange, X, Sparkles, CheckCircle2, AlertCircle, Image as ImageIcon, Headphones } from 'lucide-react'
import api, { getApiError } from '@/lib/api'
import PrintButton from '@/components/PrintButton'
import { MODE_BADGE } from '../types'

interface ParrillaModalProps {
  onClose: () => void
}

interface ParrillaDay {
  day: number
  day_name: string
  mode: string
  mode_emoji: string
  format: string
  script: string
  audio_url: string | null
  banner_url: string | null
}

interface ParrillaResult {
  days: ParrillaDay[]
  plan: string
  auto_scheduled: boolean
}

interface ParrillaStatus extends ParrillaResult {
  status: 'pending' | 'running' | 'done' | 'error'
  total_days: number
  current_day: number
  error: string | null
}

const POLL_INTERVAL_MS = 2500
// El worker tiene soft_time_limit=600s; si a los 11 min seguimos sin "done"
// algo se atoró (worker caído, cola saturada) — dejar de esperar y decírselo.
const MAX_POLL_MS = 11 * 60 * 1000

const PALETTES = [
  { key: 'promo', label: 'Azul/Rojo', colors: ['#1d3557', '#e63946'] },
  { key: 'verde', label: 'Verde', colors: ['#1b5e20', '#388e3c'] },
  { key: 'oscuro', label: 'Negro/Neón', colors: ['#121212', '#00e676'] },
  { key: 'elegante', label: 'Dorado', colors: ['#1a1a2e', '#e8c547'] },
  { key: 'naranja', label: 'Naranja', colors: ['#e65100', '#ff8f00'] },
  { key: 'morado', label: 'Morado', colors: ['#4a148c', '#7b1fa2'] },
  { key: 'azul', label: 'Azul vivo', colors: ['#0d47a1', '#1565c0'] },
  { key: 'rojo', label: 'Rojo', colors: ['#b71c1c', '#e53935'] },
]

const LAYOUTS = [
  { key: 'clasico', label: 'Clásico' },
  { key: 'centrado', label: 'Centrado' },
  { key: 'split', label: 'Split' },
  { key: 'minimal', label: 'Minimal' },
]

export function ParrillaModal({ onClose }: ParrillaModalProps) {
  const [parrillaBusinessName, setParrillaBusinessName] = useState('')
  const [parrillaIntent, setParrillaIntent] = useState('')
  const [parrillaCategory, setParrillaCategory] = useState('')
  const [parrillaContext, setParrillaContext] = useState('')
  const [parrillaCountry, setParrillaCountry] = useState('mx')
  const [parrillaSendTime, setParrillaSendTime] = useState('10:00')
  const [parrillaAutoSchedule, setParrillaAutoSchedule] = useState(false)
  const [parrillaBannerPalette, setParrillaBannerPalette] = useState('promo')
  const [parrillaBannerLayout, setParrillaBannerLayout] = useState('clasico')
  const [parrillaGenerating, setParrillaGenerating] = useState(false)
  const [parrillaResult, setParrillaResult] = useState<ParrillaResult | null>(null)
  const [parrillaError, setParrillaError] = useState('')
  const [parrillaJobId, setParrillaJobId] = useState<string | null>(null)
  const [parrillaProgress, setParrillaProgress] = useState<{ current: number; total: number } | null>(null)

  // Hace polling del job mientras esté pendiente/corriendo. Se limpia solo al
  // terminar, fallar, agotar el tiempo máximo, o si el modal se desmonta —
  // así el usuario nunca se queda sin saber qué pasó, ni el polling sigue
  // corriendo de fondo después de cerrar.
  useEffect(() => {
    if (!parrillaJobId) return

    const startedAt = Date.now()
    let cancelled = false

    const poll = async () => {
      if (cancelled) return
      try {
        const { data } = await api.get<ParrillaStatus>(`/campaigns/generate-parrilla/${parrillaJobId}`)
        if (cancelled) return

        setParrillaProgress({ current: data.current_day, total: data.total_days })
        setParrillaResult({ days: data.days, plan: data.plan, auto_scheduled: data.auto_scheduled })

        if (data.status === 'done') {
          setParrillaGenerating(false)
          setParrillaJobId(null)
        } else if (data.status === 'error') {
          setParrillaError(data.error || 'Error al generar la parrilla')
          setParrillaGenerating(false)
          setParrillaJobId(null)
        } else if (Date.now() - startedAt > MAX_POLL_MS) {
          setParrillaError('La generación está tardando más de lo normal. Revisa la sección Campañas en unos minutos — es posible que haya terminado igual.')
          setParrillaGenerating(false)
          setParrillaJobId(null)
        }
      } catch (err: unknown) {
        if (cancelled) return
        setParrillaError(getApiError(err, 'Error al consultar el progreso'))
        setParrillaGenerating(false)
        setParrillaJobId(null)
      }
    }

    poll()
    const interval = setInterval(poll, POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [parrillaJobId])

  const generateParrilla = async () => {
    if (!parrillaBusinessName || !parrillaIntent) return
    setParrillaGenerating(true)
    setParrillaError('')
    setParrillaResult(null)
    setParrillaProgress(null)
    try {
      const { data } = await api.post<{ job_id: string }>(
        '/campaigns/generate-parrilla',
        {
          business_name: parrillaBusinessName,
          intent: parrillaIntent,
          country: parrillaCountry,
          business_category: parrillaCategory || undefined,
          extra_context: parrillaContext || undefined,
          auto_schedule: parrillaAutoSchedule,
          send_time: parrillaSendTime,
          banner_palette: parrillaBannerPalette,
          banner_layout: parrillaBannerLayout,
        }
      )
      setParrillaJobId(data.job_id)
    } catch (err: unknown) {
      setParrillaError(getApiError(err, 'Error al generar parrilla'))
      setParrillaGenerating(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 dark:bg-black/80 p-4" onClick={onClose}>
      <div className="w-full max-w-5xl rounded-2xl bg-card p-6 shadow-2xl max-h-[92vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="mb-5 flex items-center justify-between border-b pb-4">
          <div>
            <h3 className="text-xl font-bold text-foreground flex items-center gap-2">
              <CalendarRange className="h-5 w-5 text-brand-500" />
              Parrilla Semanal de Radio
            </h3>
            <p className="mt-1 text-sm text-muted-foreground">
              Genera 7 días de contenido en un clic. Una estrategia completa para tus clientes.
            </p>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-gray-600 dark:hover:text-gray-400">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Formulario Izquierdo */}
          <div className="col-span-1 space-y-4 border-r pr-6">
            <div>
              <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">Nombre del negocio</label>
              <input
                type="text"
                placeholder="Ej: Pizzería Don Corleone"
                value={parrillaBusinessName}
                onChange={(e) => setParrillaBusinessName(e.target.value)}
                className="w-full rounded-lg border border-border bg-background text-foreground px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">Propósito principal de la semana</label>
              <textarea
                rows={3}
                placeholder="Ej: Anunciar nuestras nuevas pizzas veganas y la promo del 2x1 los jueves"
                value={parrillaIntent}
                onChange={(e) => setParrillaIntent(e.target.value)}
                className="w-full rounded-lg border border-border bg-background text-foreground px-3 py-2 text-sm focus:border-brand-500 focus:outline-none resize-none"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">Categoría (opcional)</label>
              <input
                type="text"
                placeholder="Ej: restaurante, zapatería"
                value={parrillaCategory}
                onChange={(e) => setParrillaCategory(e.target.value)}
                className="w-full rounded-lg border border-border bg-background text-foreground px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">Contexto extra (opcional)</label>
              <input
                type="text"
                placeholder="Ej: Premio de la trivia, temporada"
                value={parrillaContext}
                onChange={(e) => setParrillaContext(e.target.value)}
                className="w-full rounded-lg border border-border bg-background text-foreground px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
              />
            </div>
            {/* Preferencias de banner */}
            <div className="rounded-xl border border-violet-100 dark:border-violet-800 bg-violet-50 dark:bg-violet-950/30 p-4 space-y-3">
              <p className="text-sm font-medium text-violet-900 dark:text-violet-100">🖼️ Preferencias de banner</p>
              <p className="text-xs text-violet-700 dark:text-violet-300">Los días con banner mostrarán una imagen promocional con el nombre de cada contacto.</p>
              <div>
                <label className="mb-1 block text-xs font-medium text-violet-800 dark:text-violet-200">Paleta de colores</label>
                <div className="grid grid-cols-4 gap-1.5">
                  {PALETTES.map((p) => (
                    <button
                      key={p.key}
                      type="button"
                      onClick={() => setParrillaBannerPalette(p.key)}
                      className={`flex items-center gap-1 rounded border-2 px-1.5 py-1 text-[10px] font-medium transition ${
                        parrillaBannerPalette === p.key
                          ? 'border-violet-500 bg-violet-100 dark:bg-violet-900/40'
                          : 'border-transparent hover:border-violet-300'
                      }`}
                    >
                      <span className="flex gap-0.5">
                        {p.colors.map((c, i) => (
                          <span key={i} className="w-2 h-2 rounded-full inline-block" style={{ background: c }} />
                        ))}
                      </span>
                      {p.label}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-violet-800 dark:text-violet-200">Diseño</label>
                <div className="flex gap-1.5">
                  {LAYOUTS.map((l) => (
                    <button
                      key={l.key}
                      type="button"
                      onClick={() => setParrillaBannerLayout(l.key)}
                      className={`rounded border-2 px-2 py-1 text-xs font-medium transition ${
                        parrillaBannerLayout === l.key
                          ? 'border-violet-500 bg-violet-100 dark:bg-violet-900/40'
                          : 'border-transparent hover:border-violet-300'
                      }`}
                    >
                      {l.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div className="rounded-xl border border-blue-100 dark:border-blue-800 bg-blue-50 dark:bg-blue-950/30 p-4 space-y-3">
              <label className="flex cursor-pointer items-start gap-2">
                <input
                  type="checkbox"
                  checked={parrillaAutoSchedule}
                  onChange={(e) => setParrillaAutoSchedule(e.target.checked)}
                  className="mt-0.5 h-4 w-4 rounded border-border bg-background text-blue-600 dark:text-blue-300 focus:ring-blue-500"
                />
                <div>
                  <span className="text-sm font-medium text-blue-900 dark:text-blue-100">Programar envíos automáticos</span>
                  <p className="text-xs text-blue-700 dark:text-blue-300">Si está activo, se enviará cada día automáticamente a la hora elegida.</p>
                </div>
              </label>
              {parrillaAutoSchedule && (
                <div>
                  <label className="mb-1 block text-xs font-medium text-blue-800 dark:text-blue-200">Hora de envío local</label>
                  <input
                    type="time"
                    value={parrillaSendTime}
                    onChange={(e) => setParrillaSendTime(e.target.value)}
                    className="w-full rounded border border-blue-200 dark:border-blue-800 px-2 py-1.5 text-sm"
                  />
                </div>
              )}
            </div>

            {parrillaError && <p className="text-sm text-red-600">{parrillaError}</p>}

            <button
              onClick={generateParrilla}
              disabled={parrillaGenerating || !parrillaBusinessName || !parrillaIntent}
              className="w-full flex items-center justify-center gap-2 rounded-lg bg-brand-500 py-2.5 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-60 transition-colors"
            >
              <Sparkles className="h-4 w-4" />
              {parrillaGenerating
                ? parrillaProgress
                  ? `Generando día ${Math.min(parrillaProgress.current + 1, parrillaProgress.total)}/${parrillaProgress.total}...`
                  : 'Encolando...'
                : 'Generar Parrilla'}
            </button>
          </div>

          {/* Vista previa Derecha */}
          <div className="col-span-2">
            {!parrillaResult && !parrillaGenerating && (
              <div className="flex h-full flex-col items-center justify-center rounded-xl border border-dashed border-border bg-muted py-12 text-center dark:bg-gray-800">
                <CalendarRange className="h-12 w-12 text-gray-300 mb-3" />
                <p className="text-sm font-medium text-muted-foreground">Llena los datos y haz clic en Generar</p>
                <p className="mt-1 text-xs text-muted-foreground">Audios y banners visuales optimizados para cada día de la semana.</p>
              </div>
            )}
            {!parrillaResult?.days.length && parrillaGenerating && (
              <div className="flex h-full flex-col items-center justify-center rounded-xl bg-muted py-12 text-center dark:bg-gray-800">
                <div className="h-8 w-8 animate-spin rounded-full border-4 border-brand-200 border-t-brand-500 mb-4" />
                <p className="text-sm font-medium text-gray-700 dark:text-gray-300">Preparando la parrilla...</p>
                <p className="mt-1 text-xs text-muted-foreground">Claude escribe guiones, genera banners y sintetiza voz — cada día va apareciendo aquí conforme termina.</p>
              </div>
            )}
            {!!parrillaResult?.days.length && (
              <div className="space-y-4">
                {parrillaGenerating && (
                  <div className="flex items-center gap-3 bg-blue-50 dark:bg-blue-950/30 px-4 py-3 rounded-lg border border-blue-200 dark:border-blue-800">
                    <div className="h-4 w-4 flex-shrink-0 animate-spin rounded-full border-2 border-blue-200 border-t-blue-600" />
                    <span className="text-sm font-medium text-blue-800 dark:text-blue-200">
                      Generando día {Math.min((parrillaProgress?.current ?? 0) + 1, parrillaProgress?.total ?? 7)}/{parrillaProgress?.total ?? 7}...
                    </span>
                  </div>
                )}
                {parrillaError && !parrillaGenerating && (
                  <div className="flex items-center gap-2 bg-red-50 dark:bg-red-950/30 px-4 py-3 rounded-lg border border-red-200 dark:border-red-800">
                    <AlertCircle className="h-5 w-5 text-red-600 flex-shrink-0" />
                    <span className="text-sm font-medium text-red-800 dark:text-red-200">{parrillaError}</span>
                  </div>
                )}
                {!parrillaGenerating && !parrillaError && (
                <div className="flex items-center justify-between bg-green-50 dark:bg-green-950/30 px-4 py-3 rounded-lg border border-green-200 dark:border-green-800">
                  <div className="flex items-center gap-2">
                    <CheckCircle2 className="h-5 w-5 text-green-600" />
                    <span className="text-sm font-medium text-green-800 dark:text-green-200">
                      {parrillaResult.auto_scheduled ? '¡Parrilla generada y programada!' : '¡Parrilla generada!'}
                    </span>
                  </div>
                  <span className="text-xs font-semibold text-green-700 dark:text-green-300 uppercase bg-green-200 dark:bg-green-800 px-2 py-0.5 rounded-full">
                    Plan {parrillaResult.plan}
                  </span>
                </div>
                )}

                {/* Print header — visible only in @media print */}
                <div className="print-only">
                  <div className="print-header">
                    <h2>Parrilla de contenido — {parrillaBusinessName}</h2>
                    {parrillaIntent && <p>Propósito: {parrillaIntent}</p>}
                    {parrillaCategory && <p>Categoría: {parrillaCategory}</p>}
                  </div>
                </div>

                <div className="flex justify-end no-print">
                  <PrintButton />
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-h-[500px] overflow-y-auto pr-2">
                  {parrillaResult.days.map((d) => (
                    <div key={d.day} className="rounded-xl border border-border bg-card p-3 shadow-sm flex flex-col print-keep-together">
                      <div className="flex items-center justify-between mb-2">
                        <span className="font-semibold text-gray-800 dark:text-gray-200">{d.day_name}</span>
                        <div className="flex items-center gap-1.5">
                          {d.format === 'banner' ? (
                            <span className="text-xs font-medium text-violet-600 dark:text-violet-400 flex items-center gap-1 bg-violet-50 dark:bg-violet-950/30 px-2 py-0.5 rounded-full">
                              <ImageIcon className="h-3 w-3" /> Banner
                            </span>
                          ) : (
                            <span className="text-xs font-medium text-emerald-600 dark:text-emerald-400 flex items-center gap-1 bg-emerald-50 dark:bg-emerald-950/30 px-2 py-0.5 rounded-full">
                              <Headphones className="h-3 w-3" /> Audio
                            </span>
                          )}
                          <span className="text-xs font-medium text-muted-foreground flex items-center gap-1 bg-muted px-2 py-0.5 rounded-full dark:bg-gray-800 dark:text-gray-300">
                            {d.mode_emoji} {MODE_BADGE[d.mode]?.replace(/[^a-zA-Z\s]/g, '').trim()}
                          </span>
                        </div>
                      </div>
                      {d.format === 'banner' ? (
                        d.banner_url ? (
                          <img src={d.banner_url} alt={`Banner ${d.day_name}`} className="w-full rounded-lg mb-2 border border-border" />
                        ) : (
                          <div className="flex items-center gap-1 text-xs text-red-500 mb-2 bg-red-50 dark:bg-red-950/30 p-2 rounded">
                            <AlertCircle className="h-3 w-3" /> Error al generar banner
                          </div>
                        )
                      ) : (
                        d.audio_url ? (
                          <audio controls src={d.audio_url} className="w-full h-8 mb-2" />
                        ) : (
                          <div className="flex items-center gap-1 text-xs text-red-500 mb-2 bg-red-50 dark:bg-red-950/30 p-1 rounded">
                            <AlertCircle className="h-3 w-3" /> Error al generar audio
                          </div>
                        )
                      )}
                      <div className="text-xs text-gray-600 dark:text-gray-400 bg-muted p-2 rounded border border-border flex-1 overflow-y-auto max-h-24 print-no-overflow dark:bg-gray-800">
                        {d.script}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
