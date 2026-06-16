import { useState } from 'react'
import { CalendarRange, X, Sparkles, CheckCircle2, AlertCircle } from 'lucide-react'
import api, { getApiError } from '@/lib/api'
import PrintButton from '@/components/PrintButton'
import { MODE_BADGE } from '../types'

interface ParrillaModalProps {
  onClose: () => void
}

interface ParrillaResult {
  days: {
    day: number
    day_name: string
    mode: string
    mode_emoji: string
    script: string
    audio_url: string | null
  }[]
  plan: string
  auto_scheduled: boolean
}

export function ParrillaModal({ onClose }: ParrillaModalProps) {
  const [parrillaBusinessName, setParrillaBusinessName] = useState('')
  const [parrillaIntent, setParrillaIntent] = useState('')
  const [parrillaCategory, setParrillaCategory] = useState('')
  const [parrillaContext, setParrillaContext] = useState('')
  const [parrillaCountry, setParrillaCountry] = useState('mx')
  const [parrillaSendTime, setParrillaSendTime] = useState('10:00')
  const [parrillaAutoSchedule, setParrillaAutoSchedule] = useState(false)
  const [parrillaGenerating, setParrillaGenerating] = useState(false)
  const [parrillaResult, setParrillaResult] = useState<ParrillaResult | null>(null)
  const [parrillaError, setParrillaError] = useState('')

  const generateParrilla = async () => {
    if (!parrillaBusinessName || !parrillaIntent) return
    setParrillaGenerating(true)
    setParrillaError('')
    try {
      const { data } = await api.post(
        '/campaigns/generate-parrilla',
        {
          business_name: parrillaBusinessName,
          intent: parrillaIntent,
          country: parrillaCountry,
          business_category: parrillaCategory || undefined,
          extra_context: parrillaContext || undefined,
          auto_schedule: parrillaAutoSchedule,
          send_time: parrillaSendTime,
        },
        { timeout: 120000 }
      )
      setParrillaResult(data)
    } catch (err: unknown) {
      setParrillaError(getApiError(err, 'Error al generar parrilla'))
    } finally {
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
                className="w-full rounded-lg border border-border px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">Propósito principal de la semana</label>
              <textarea
                rows={3}
                placeholder="Ej: Anunciar nuestras nuevas pizzas veganas y la promo del 2x1 los jueves"
                value={parrillaIntent}
                onChange={(e) => setParrillaIntent(e.target.value)}
                className="w-full rounded-lg border border-border px-3 py-2 text-sm focus:border-brand-500 focus:outline-none resize-none"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">Categoría (opcional)</label>
              <input
                type="text"
                placeholder="Ej: restaurante, zapatería"
                value={parrillaCategory}
                onChange={(e) => setParrillaCategory(e.target.value)}
                className="w-full rounded-lg border border-border px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">Contexto extra (opcional)</label>
              <input
                type="text"
                placeholder="Ej: Premio de la trivia, temporada"
                value={parrillaContext}
                onChange={(e) => setParrillaContext(e.target.value)}
                className="w-full rounded-lg border border-border px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
              />
            </div>
            <div className="rounded-xl border border-blue-100 dark:border-blue-800 bg-blue-50 dark:bg-blue-950/30 p-4 space-y-3">
              <label className="flex cursor-pointer items-start gap-2">
                <input
                  type="checkbox"
                  checked={parrillaAutoSchedule}
                  onChange={(e) => setParrillaAutoSchedule(e.target.checked)}
                  className="mt-0.5 h-4 w-4 rounded border-border text-blue-600 dark:text-blue-300 focus:ring-blue-500"
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
              {parrillaGenerating ? 'Generando 7 días...' : 'Generar Parrilla'}
            </button>
          </div>

          {/* Vista previa Derecha */}
          <div className="col-span-2">
            {!parrillaResult && !parrillaGenerating && (
              <div className="flex h-full flex-col items-center justify-center rounded-xl border border-dashed border-border bg-muted py-12 text-center dark:bg-gray-800">
                <CalendarRange className="h-12 w-12 text-gray-300 mb-3" />
                <p className="text-sm font-medium text-muted-foreground">Llena los datos y haz clic en Generar</p>
                <p className="mt-1 text-xs text-muted-foreground">Crearemos 7 cuñas distintas optimizadas para cada día.</p>
              </div>
            )}
            {parrillaGenerating && (
              <div className="flex h-full flex-col items-center justify-center rounded-xl bg-muted py-12 text-center dark:bg-gray-800">
                <div className="h-8 w-8 animate-spin rounded-full border-4 border-brand-200 border-t-brand-500 mb-4" />
                <p className="text-sm font-medium text-gray-700 dark:text-gray-300">Escribiendo y grabando 7 cuñas...</p>
                <p className="mt-1 text-xs text-muted-foreground">Esto puede tardar un poco (Claude + Text-to-Speech)</p>
              </div>
            )}
            {parrillaResult && (
              <div className="space-y-4">
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
                        <span className="text-xs font-medium text-muted-foreground flex items-center gap-1 bg-muted px-2 py-0.5 rounded-full dark:bg-gray-800 dark:text-gray-300">
                          {d.mode_emoji} {MODE_BADGE[d.mode]?.replace(/[^a-zA-Z\s]/g, '').trim()}
                        </span>
                      </div>
                      {d.audio_url ? (
                        <audio controls src={d.audio_url} className="w-full h-8 mb-2" />
                      ) : (
                        <div className="flex items-center gap-1 text-xs text-red-500 mb-2 bg-red-50 dark:bg-red-950/30 p-1 rounded">
                          <AlertCircle className="h-3 w-3" /> Error al generar audio
                        </div>
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
