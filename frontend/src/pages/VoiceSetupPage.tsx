import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import api, { getApiError } from '@/lib/api'
import SEO from '@/components/SEO'
import { canRecordVoice, micErrorMessage, startVoiceRecording, type VoiceSession } from '@/lib/voiceRecorder'
import { Check, ChevronDown, Keyboard, Loader2, Mic, PartyPopper, Square, X } from 'lucide-react'

// "Cuéntale a tu bot de tu negocio": el dueño habla (o escribe), la IA ordena
// lo que dijo y él lo aprueba antes de guardar. Backend: api/v1/voice_setup.py.
// Lecciones de las pruebas de campo de Raíz (TecNM Tlaxiaco): un solo botón
// grande, que se vea que es seguro tocarlo, y nada se guarda sin su "sí".

interface Service {
  name: string
  price: number | null
  description: string | null
}

interface Profile {
  business_category: string | null
  city: string | null
  address: string | null
  business_hours: Record<string, [string, string] | null> | null
  services: Service[]
  payment_methods: string[]
  policies: string[]
  faqs: { q: string; a: string }[]
  notes: string[]
}

interface ListenResult {
  transcript: string
  profile: Profile
  hours_text: string | null
  instructions_preview: string
  replaces_existing_instructions: boolean
}

interface ApplyResult {
  products_created: number
  products_updated: number
  hours_set: boolean
}

type Step = 'intro' | 'recording' | 'processing' | 'review' | 'saving' | 'done'

const MAX_SECONDS = 300
const DAY_LABELS: Record<string, string> = {
  mon: 'Lunes', tue: 'Martes', wed: 'Miércoles', thu: 'Jueves', fri: 'Viernes', sat: 'Sábado', sun: 'Domingo',
}
const PROMPTS = ['Qué vendes y a qué precio', 'Tu horario', 'Dónde estás', 'Cómo te pagan', 'Lo que siempre te preguntan']

const money = (p: number | null) =>
  p === null ? 'Sin precio' : new Intl.NumberFormat('es-MX', { style: 'currency', currency: 'MXN', maximumFractionDigits: p % 1 ? 2 : 0 }).format(p)
const clock = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`

export default function VoiceSetupPage() {
  const [step, setStep] = useState<Step>('intro')
  const [result, setResult] = useState<ListenResult | null>(null)
  const [applied, setApplied] = useState<ApplyResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [typing, setTyping] = useState(false)
  const [text, setText] = useState('')
  const [seconds, setSeconds] = useState(0)
  const [volume, setVolume] = useState(0)
  const [showTranscript, setShowTranscript] = useState(false)
  const session = useRef<VoiceSession | null>(null)
  const timer = useRef<ReturnType<typeof setInterval> | null>(null)
  const micAvailable = canRecordVoice()

  useEffect(() => () => {
    session.current?.cancel()
    if (timer.current) clearInterval(timer.current)
  }, [])

  const send = async (form: FormData) => {
    setStep('processing')
    setError(null)
    if (result) form.append('draft', JSON.stringify(result.profile))
    try {
      const { data } = await api.post<ListenResult>('/voice-setup/listen', form)
      setResult(data)
      setStep('review')
      setTyping(false)
      setText('')
    } catch (err) {
      setError(getApiError(err, 'No pude ordenar lo que me contaste. Intenta de nuevo.'))
      setStep(result ? 'review' : 'intro')
    }
  }

  const stopRecording = async () => {
    if (timer.current) clearInterval(timer.current)
    const s = session.current
    session.current = null
    if (!s) return
    const rec = await s.stop()
    if (rec.seconds < 2) {
      setError('Fue muy cortito. Toca el micrófono y cuéntame un poco más.')
      setStep(result ? 'review' : 'intro')
      return
    }
    const form = new FormData()
    const ext = rec.mimeType.includes('mp4') ? 'mp4' : rec.mimeType.includes('ogg') ? 'ogg' : 'webm'
    form.append('audio', rec.blob, `nota.${ext}`)
    await send(form)
  }

  const startRecording = async () => {
    setError(null)
    try {
      session.current = await startVoiceRecording(setVolume)
    } catch (err) {
      setError(micErrorMessage(err))
      setTyping(true)
      return
    }
    setSeconds(0)
    setStep('recording')
    timer.current = setInterval(() => setSeconds((s) => s + 1), 1000)
  }

  // Tope de 5 minutos: se corta solo y se manda lo grabado.
  useEffect(() => {
    if (step === 'recording' && seconds >= MAX_SECONDS) void stopRecording()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, seconds])

  const cancelRecording = () => {
    if (timer.current) clearInterval(timer.current)
    session.current?.cancel()
    session.current = null
    setStep(result ? 'review' : 'intro')
  }

  const sendText = async () => {
    if (!text.trim()) return
    const form = new FormData()
    form.append('text', text)
    await send(form)
  }

  const removeService = (i: number) =>
    setResult((r) => r && { ...r, profile: { ...r.profile, services: r.profile.services.filter((_, j) => j !== i) } })

  const applyProfile = async () => {
    if (!result) return
    setStep('saving')
    setError(null)
    try {
      const { data } = await api.post<ApplyResult>('/voice-setup/apply', { profile: result.profile })
      setApplied(data)
      setStep('done')
    } catch (err) {
      setError(getApiError(err, 'No se pudo guardar. Intenta de nuevo.'))
      setStep('review')
    }
  }

  return (
    <>
      <SEO title="Cuéntale a tu bot" noIndex />
      <div className="mx-auto max-w-2xl space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-foreground sm:text-3xl">Cuéntale a tu bot de tu negocio</h1>
          <p className="mt-2 text-base text-muted-foreground">
            Habla como si le explicaras a un empleado nuevo. En un par de minutos tu bot queda listo para atender.
          </p>
          {step === 'intro' && (
            <p className="mt-1 text-base text-muted-foreground">No se publica nada hasta que tú lo apruebes.</p>
          )}
        </div>

        {error && (
          <div role="alert" className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-base text-rose-700 dark:border-rose-900 dark:bg-rose-950/30 dark:text-rose-300">
            {error}
          </div>
        )}

        {(step === 'intro' || step === 'recording') && !typing && (
          <RecorderCard
            recording={step === 'recording'}
            seconds={seconds}
            volume={volume}
            micAvailable={micAvailable}
            isCorrection={!!result}
            onStart={startRecording}
            onStop={stopRecording}
            onCancel={cancelRecording}
            onType={() => setTyping(true)}
          />
        )}

        {typing && (step === 'intro' || step === 'review') && (
          <div className="rounded-2xl border border-border bg-card p-5">
            <label htmlFor="voice-setup-text" className="text-base font-semibold text-foreground">
              {result ? 'Escribe lo que quieres corregir o agregar' : 'Escríbelo como lo dirías'}
            </label>
            <textarea
              id="voice-setup-text"
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={6}
              maxLength={6000}
              placeholder="Ej. Abrimos de lunes a sábado de 10 a 8. El corte cuesta 150 y la barba 100. Aceptamos efectivo y transferencia…"
              className="mt-2 w-full rounded-xl border border-border bg-background p-3 text-base text-foreground"
            />
            <div className="mt-3 flex flex-wrap gap-2">
              <button onClick={sendText} disabled={!text.trim()} className="rounded-xl bg-brand-500 px-5 py-3 text-base font-semibold text-white hover:bg-brand-600 disabled:opacity-50">
                {result ? 'Aplicar cambio' : 'Ordenar mi información'}
              </button>
              {micAvailable && (
                <button onClick={() => setTyping(false)} className="rounded-xl border border-border px-5 py-3 text-base font-semibold text-foreground hover:bg-muted">
                  Mejor lo digo en voz
                </button>
              )}
            </div>
          </div>
        )}

        {(step === 'processing' || step === 'saving') && (
          <div className="flex flex-col items-center gap-3 rounded-2xl border border-border bg-card p-10 text-center">
            <Loader2 className="h-10 w-10 animate-spin text-brand-500" />
            <p className="text-lg font-semibold text-foreground">
              {step === 'processing' ? 'Ordenando lo que me contaste…' : 'Configurando tu bot…'}
            </p>
            {step === 'processing' && <p className="text-base text-muted-foreground">Tarda unos segundos.</p>}
          </div>
        )}

        {step === 'review' && result && !typing && (
          <ReviewCard
            result={result}
            showTranscript={showTranscript}
            onToggleTranscript={() => setShowTranscript((v) => !v)}
            onRemoveService={removeService}
            onCorrectVoice={micAvailable ? startRecording : undefined}
            onCorrectText={() => setTyping(true)}
            onApply={applyProfile}
          />
        )}

        {step === 'done' && applied && <DoneCard applied={applied} />}
      </div>
    </>
  )
}

function RecorderCard({
  recording, seconds, volume, micAvailable, isCorrection, onStart, onStop, onCancel, onType,
}: {
  recording: boolean
  seconds: number
  volume: number
  micAvailable: boolean
  isCorrection: boolean
  onStart: () => void
  onStop: () => void
  onCancel: () => void
  onType: () => void
}) {
  return (
    <div className="flex flex-col items-center rounded-2xl border border-border bg-card p-6 text-center sm:p-8">
      {!recording && !isCorrection && (
        <ul className="mb-6 flex flex-wrap justify-center gap-2">
          {PROMPTS.map((p) => (
            <li key={p} className="rounded-full bg-muted px-3 py-1.5 text-sm font-medium text-foreground">{p}</li>
          ))}
        </ul>
      )}

      {micAvailable ? (
        <>
          <div className="relative flex h-32 w-32 items-center justify-center">
            {/* Pulso suave: le dice al dueño que es seguro tocarlo (prueba de campo, Tijaltepec). */}
            {!recording && <span className="absolute inset-2 animate-ping rounded-full bg-brand-500/20" />}
            {recording && (
              <span
                className="absolute rounded-full bg-rose-500/20 transition-all duration-100"
                style={{ inset: `${Math.max(0, 12 - volume * 12)}px` }}
              />
            )}
            <button
              onClick={recording ? onStop : onStart}
              aria-label={recording ? 'Terminar de grabar' : 'Tocar y hablar'}
              className={`relative flex h-28 w-28 items-center justify-center rounded-full text-white shadow-xl transition-transform active:scale-95 ${
                recording ? 'bg-rose-500 hover:bg-rose-600' : 'bg-brand-500 hover:bg-brand-600'
              }`}
            >
              {recording ? <Square className="h-10 w-10" fill="currentColor" /> : <Mic className="h-12 w-12" />}
            </button>
          </div>
          <p className="mt-4 text-lg font-semibold text-foreground">
            {recording ? `Te escucho… ${clock(seconds)}` : isCorrection ? 'Toca y dime qué cambiar' : 'Toca y habla'}
          </p>
          <p className="mt-1 text-base text-muted-foreground">
            {recording ? 'Cuando termines, toca el botón rojo.' : 'Habla con calma, como en una nota de voz.'}
          </p>
          {recording ? (
            <button onClick={onCancel} className="mt-4 text-base font-medium text-muted-foreground underline">
              Cancelar
            </button>
          ) : (
            <button onClick={onType} className="mt-5 inline-flex items-center gap-2 text-base font-medium text-muted-foreground hover:text-foreground">
              <Keyboard className="h-5 w-5" /> ¿Prefieres escribir?
            </button>
          )}
        </>
      ) : (
        <button onClick={onType} className="rounded-xl bg-brand-500 px-5 py-3 text-base font-semibold text-white">
          Este navegador no permite grabar — escríbelo aquí
        </button>
      )}
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="border-t border-border pt-4 first:border-t-0 first:pt-0">
      <h3 className="text-sm font-bold uppercase tracking-wide text-muted-foreground">{title}</h3>
      <div className="mt-2 text-base text-foreground">{children}</div>
    </div>
  )
}

function ReviewCard({
  result, showTranscript, onToggleTranscript, onRemoveService, onCorrectVoice, onCorrectText, onApply,
}: {
  result: ListenResult
  showTranscript: boolean
  onToggleTranscript: () => void
  onRemoveService: (i: number) => void
  onCorrectVoice?: () => void
  onCorrectText: () => void
  onApply: () => void
}) {
  const p = result.profile
  const empty = !result.instructions_preview
  return (
    <div className="space-y-4">
      <div className="space-y-4 rounded-2xl border border-border bg-card p-5">
        <p className="text-lg font-semibold text-foreground">Esto es lo que entendí. ¿Está bien?</p>

        {empty && <p className="text-base text-muted-foreground">No alcancé a sacar datos del negocio. Intenta contarme qué vendes, precios u horario.</p>}

        {(p.address || p.city) && (
          <Section title="Dónde estás">{[p.address, p.city].filter(Boolean).join(', ')}</Section>
        )}

        {p.business_hours && (
          <Section title="Horario">
            <ul className="grid grid-cols-1 gap-1 sm:grid-cols-2">
              {Object.entries(p.business_hours).map(([day, rng]) => (
                <li key={day} className="flex justify-between gap-3 rounded-lg bg-muted/50 px-3 py-1.5">
                  <span>{DAY_LABELS[day]}</span>
                  <span className={rng ? 'font-semibold' : 'text-muted-foreground'}>{rng ? `${rng[0]} – ${rng[1]}` : 'Cerrado'}</span>
                </li>
              ))}
            </ul>
          </Section>
        )}

        {p.services.length > 0 && (
          <Section title="Lo que vendes">
            <ul className="divide-y divide-border">
              {p.services.map((s, i) => (
                <li key={`${s.name}-${i}`} className="flex items-center justify-between gap-3 py-2">
                  <div className="min-w-0">
                    <p className="font-medium">{s.name}</p>
                    {s.description && <p className="text-sm text-muted-foreground">{s.description}</p>}
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <span className="font-semibold">{money(s.price)}</span>
                    <button onClick={() => onRemoveService(i)} aria-label={`Quitar ${s.name}`} className="rounded-lg p-2 text-muted-foreground hover:bg-muted hover:text-rose-500">
                      <X className="h-4 w-4" />
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          </Section>
        )}

        {p.payment_methods.length > 0 && <Section title="Cómo te pagan">{p.payment_methods.join(' · ')}</Section>}

        {p.policies.length > 0 && (
          <Section title="Tus reglas">
            <ul className="list-disc space-y-1 pl-5">{p.policies.map((x) => <li key={x}>{x}</li>)}</ul>
          </Section>
        )}

        {p.faqs.length > 0 && (
          <Section title="Lo que te preguntan">
            <ul className="space-y-2">
              {p.faqs.map((f) => (
                <li key={f.q}>
                  <p className="font-medium">{f.q}</p>
                  <p className="text-muted-foreground">{f.a}</p>
                </li>
              ))}
            </ul>
          </Section>
        )}

        {p.notes.length > 0 && (
          <Section title="Otros datos">
            <ul className="list-disc space-y-1 pl-5">{p.notes.map((x) => <li key={x}>{x}</li>)}</ul>
          </Section>
        )}

        <button onClick={onToggleTranscript} className="inline-flex items-center gap-1 text-sm font-medium text-muted-foreground">
          Lo que escuché <ChevronDown className={`h-4 w-4 transition-transform ${showTranscript ? 'rotate-180' : ''}`} />
        </button>
        {showTranscript && <p className="rounded-lg bg-muted/50 p-3 text-sm italic text-muted-foreground">“{result.transcript}”</p>}
      </div>

      {result.replaces_existing_instructions && !empty && (
        <p className="rounded-xl bg-amber-50 p-3 text-sm text-amber-800 dark:bg-amber-950/30 dark:text-amber-300">
          Esto reemplaza las instrucciones que tu bot tenía antes. Tus productos actuales se conservan.
        </p>
      )}

      <div className="flex flex-col gap-3 sm:flex-row">
        <button
          onClick={onApply}
          disabled={empty}
          className="inline-flex flex-1 items-center justify-center gap-2 rounded-xl bg-brand-500 px-5 py-4 text-lg font-bold text-white shadow-md hover:bg-brand-600 disabled:opacity-50"
        >
          <Check className="h-6 w-6" /> Así está bien, configura mi bot
        </button>
        {onCorrectVoice && (
          <button onClick={onCorrectVoice} className="inline-flex items-center justify-center gap-2 rounded-xl border border-border px-5 py-4 text-base font-semibold text-foreground hover:bg-muted">
            <Mic className="h-5 w-5" /> Corregir o agregar
          </button>
        )}
        <button onClick={onCorrectText} className="inline-flex items-center justify-center gap-2 rounded-xl border border-border px-5 py-4 text-base font-semibold text-foreground hover:bg-muted">
          <Keyboard className="h-5 w-5" /> Escribir
        </button>
      </div>
    </div>
  )
}

function DoneCard({ applied }: { applied: ApplyResult }) {
  const lines = [
    'Tu bot ya conoce tu negocio y contesta con esta información.',
    applied.hours_set && 'Tu horario también se usa para agendar citas.',
    applied.products_created > 0 &&
      `Agregamos ${applied.products_created} producto${applied.products_created === 1 ? '' : 's'} a tu catálogo.`,
    applied.products_updated > 0 &&
      `Actualizamos el precio de ${applied.products_updated} producto${applied.products_updated === 1 ? '' : 's'}.`,
  ].filter(Boolean) as string[]
  return (
    <div className="rounded-2xl border border-green-200 bg-green-50 p-6 dark:border-green-900 dark:bg-green-950/30">
      <PartyPopper className="h-10 w-10 text-green-600" />
      <p className="mt-3 text-xl font-bold text-foreground">¡Listo! Tu bot quedó configurado</p>
      <ul className="mt-3 space-y-1 text-base text-foreground">{lines.map((l) => <li key={l}>✓ {l}</li>)}</ul>
      <div className="mt-5 flex flex-wrap gap-2">
        <Link to="/app/products" className="rounded-xl bg-brand-500 px-4 py-3 text-base font-semibold text-white hover:bg-brand-600">Ver mi catálogo</Link>
        <Link to="/app/settings" className="rounded-xl border border-border px-4 py-3 text-base font-semibold text-foreground hover:bg-muted">Ver o editar a mano</Link>
        <Link to="/app/dashboard" className="rounded-xl border border-border px-4 py-3 text-base font-semibold text-foreground hover:bg-muted">Ir al inicio</Link>
      </div>
    </div>
  )
}
