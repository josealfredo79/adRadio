import { useEffect, useRef, useState } from 'react'
import api, { getApiError } from '@/lib/api'
import SEO from '@/components/SEO'
import { type FaceMood } from '@/components/BotFace'
import MeshHead3D from '@/components/MeshHead3D'
import { useAuth } from '@/contexts/AuthContext'
import { canRecordVoice, micErrorMessage, startVoiceRecording, type VoiceSession } from '@/lib/voiceRecorder'
import { useSpeaker } from '@/lib/useSpeaker'
import { Camera, Check, CheckCircle2, Keyboard, Mic, Square, Volume2, VolumeX, X } from 'lucide-react'

// "Habla con IaRadio": el dueño trabaja con IaRadio hablando, sin buscar en el
// menú. Le pide algo con su voz ("¿qué citas tengo hoy?", "crea un cupón del
// 10 %"), el Copiloto lo hace y le contesta en voz alta con la cabeza que
// mueve los labios. Lo importante (campañas, cupones, citas, productos,
// horario) siempre espera su "sí": con la voz o con dos botones grandes. Backend: POST /copilot/voice
// (api/v1/copilot.py), que transcribe y usa el mismo Copiloto que el chat.

interface PendingConfirmation {
  confirmation_id: string
  tool: string
  summary: string
}

interface CopilotAction {
  tool: string
  summary: string
}

interface VoiceResult {
  transcript?: string
  reply: string
  actions: CopilotAction[]
  pending_confirmation: PendingConfirmation | null
}

interface Turn {
  role: 'user' | 'assistant'
  content: string
}

type Step = 'idle' | 'recording' | 'processing'

const MAX_SECONDS = 120
const MAX_HISTORY = 20
const SUGGESTIONS = [
  '¿Qué citas tengo hoy?',
  '¿Llegaron pedidos hoy?',
  '¿Cuánto tengo mis productos?',
  'El sábado abro de 9 a 2',
  'Crea un cupón del 10 % para esta semana',
]

/** Lo que se dice en voz alta: sin marcas de formato y no muy largo. */
function speakable(text: string): string {
  return text.replace(/[*_#`>]/g, '').replace(/^\s*[-•]\s*/gm, '').replace(/\s+/g, ' ').trim().slice(0, 600)
}

export default function TalkPage() {
  const { user } = useAuth()
  const greeting =
    `¡Hola${user?.business_name ? `, ${user.business_name}` : ''}! Soy IaRadio. Dime qué necesitas: ` +
    'puedo ver tus citas, pedidos y clientes, cambiar precios u horario, agregar un producto con foto, ' +
    'crear cupones o lanzar una promoción.'
  const [step, setStep] = useState<Step>('idle')
  const [bubble, setBubble] = useState(greeting)
  const [heard, setHeard] = useState('')
  const [pending, setPending] = useState<PendingConfirmation | null>(null)
  const [done, setDone] = useState<CopilotAction[]>([])
  const [history, setHistory] = useState<Turn[]>([])
  const [error, setError] = useState(false)
  const [typing, setTyping] = useState(false)
  const [text, setText] = useState('')
  const [seconds, setSeconds] = useState(0)
  // Foto de un producto, tomada con el botón de la cámara: se sube luego luego
  // y viaja con lo siguiente que diga ("agrega este producto, tinte a 450").
  const [photo, setPhoto] = useState<{ url: string; preview: string } | null>(null)
  const [uploading, setUploading] = useState(false)
  const photoInput = useRef<HTMLInputElement>(null)
  const session = useRef<VoiceSession | null>(null)
  const timer = useRef<ReturnType<typeof setInterval> | null>(null)
  const speaker = useSpeaker()
  const micAvailable = canRecordVoice()
  // En celular un poco más chica, para que el micrófono quede a la vista.
  const [faceSize] = useState(() => (window.innerWidth < 640 ? 190 : 240))

  useEffect(() => () => {
    session.current?.cancel()
    if (timer.current) clearInterval(timer.current)
  }, [])

  const mood: FaceMood =
    step === 'recording' ? 'listening'
      : step === 'processing' ? 'thinking'
        : error ? 'confused'
          : speaker.speaking ? 'speaking'
            : 'idle'

  const say = (line: string) => {
    setBubble(line)
    void speaker.speak(speakable(line))
  }

  const handle = (said: string | undefined, data: VoiceResult) => {
    setError(false)
    if (said) setHeard(said)
    setPending(data.pending_confirmation)
    if (data.actions.length) setDone((d) => [...data.actions, ...d].slice(0, 6))
    setHistory((h) => [
      ...h,
      ...(said ? [{ role: 'user' as const, content: said }] : []),
      { role: 'assistant' as const, content: data.reply },
    ].slice(-MAX_HISTORY))
    say(data.reply)
  }

  const fail = (err: unknown) => {
    const msg = getApiError(err, 'No te entendí bien. ¿Me lo repites?')
    setError(true)
    say(msg)
  }

  const send = async (form: FormData) => {
    setStep('processing')
    setBubble('Déjame ver…')
    if (history.length) form.append('history', JSON.stringify(history))
    if (pending) form.append('confirmation_id', pending.confirmation_id)
    if (photo) form.append('photo_url', photo.url)
    try {
      const { data } = await api.post<VoiceResult>('/copilot/voice', form)
      handle(data.transcript, data)
      setTyping(false)
      setText('')
      clearPhoto()
    } catch (err) {
      fail(err)
    } finally {
      setStep('idle')
    }
  }

  const sendText = async (value: string) => {
    speaker.unlock()
    if (!value.trim()) return
    const form = new FormData()
    form.append('text', value.trim())
    await send(form)
  }

  const clearPhoto = () => {
    if (photo) URL.revokeObjectURL(photo.preview)
    setPhoto(null)
  }

  const pickPhoto = async (file: File | undefined) => {
    if (!file) return
    speaker.unlock()
    setUploading(true)
    try {
      const form = new FormData()
      form.append('file', file)
      const { data } = await api.post<{ url: string }>('/copilot/photo', form)
      clearPhoto()
      setPhoto({ url: data.url, preview: URL.createObjectURL(file) })
      say('¡Buena foto! Ahora dime qué es y en cuánto lo vendes, por ejemplo: “agrega este producto, tinte a 450”.')
    } catch (err) {
      fail(err)
    } finally {
      setUploading(false)
      if (photoInput.current) photoInput.current.value = ''
    }
  }

  const startRecording = async () => {
    speaker.unlock() // dentro del toque: iPhone deja hablar a la cabeza después
    speaker.stop()
    setError(false)
    try {
      session.current = await startVoiceRecording()
    } catch (err) {
      setError(true)
      setBubble(micErrorMessage(err))
      setTyping(true)
      return
    }
    setSeconds(0)
    setBubble(pending ? 'Te escucho… ¿lo hago? Dime sí o no.' : 'Te escucho…')
    setStep('recording')
    timer.current = setInterval(() => setSeconds((s) => s + 1), 1000)
  }

  const stopRecording = async () => {
    if (timer.current) clearInterval(timer.current)
    const s = session.current
    session.current = null
    if (!s) return
    const rec = await s.stop()
    if (rec.seconds < 1) {
      setStep('idle')
      say('No alcancé a oírte. Toca el micrófono y dime qué necesitas.')
      return
    }
    const form = new FormData()
    const ext = rec.mimeType.includes('mp4') ? 'mp4' : rec.mimeType.includes('ogg') ? 'ogg' : 'webm'
    form.append('audio', rec.blob, `orden.${ext}`)
    await send(form)
  }

  // Tope de 2 minutos: se corta solo y se manda lo grabado.
  useEffect(() => {
    if (step === 'recording' && seconds >= MAX_SECONDS) void stopRecording()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, seconds])

  const answer = async (approve: boolean) => {
    if (!pending) return
    speaker.unlock()
    speaker.stop()
    setStep('processing')
    setBubble(approve ? 'Va, lo hago…' : 'Va, no hago nada.')
    try {
      const { data } = await api.post<VoiceResult>('/copilot/confirm', { confirmation_id: pending.confirmation_id, approve })
      handle(approve ? 'Sí, hazlo' : 'No', data)
    } catch (err) {
      setPending(null)
      fail(err)
    } finally {
      setStep('idle')
    }
  }

  const busy = step !== 'idle' || uploading

  return (
    <>
      <SEO title="Habla con IaRadio" noIndex />
      <div className="mx-auto max-w-2xl space-y-5">
        <div>
          <h1 className="text-2xl font-bold text-foreground sm:text-3xl">Habla con IaRadio</h1>
          <p className="mt-1 text-base text-muted-foreground">
            Pídele lo que necesites con tu voz, como si le hablaras a tu asistente. Antes de mandar o crear algo, te pregunta.
          </p>
        </div>

        <div className="relative flex flex-col items-center rounded-3xl border border-border bg-card px-4 pb-6 pt-4 text-center shadow-sm">
          <button
            onClick={() => speaker.setMuted(!speaker.muted)}
            aria-label={speaker.muted ? 'Activar la voz' : 'Silenciar la voz'}
            title={speaker.muted ? 'Activar la voz' : 'Silenciar la voz'}
            className="absolute right-4 top-4 z-10 rounded-full p-2 text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            {speaker.muted ? <VolumeX className="h-5 w-5" /> : <Volume2 className="h-5 w-5" />}
          </button>

          <div className="rounded-3xl bg-[#0a0f2e] px-3 pt-2">
            <MeshHead3D mood={mood} getLevel={speaker.level} size={faceSize} />
            {/* Crédito que pide la licencia CC BY 3.0 del escaneo de la cabeza */}
            <p className="pb-1.5 text-center text-[10px] text-white/30">
              Cabeza 3D: escaneo de{' '}
              <a href="https://www.ir-ltd.net/" target="_blank" rel="noopener noreferrer" className="underline hover:text-white/60">Lee Perry-Smith</a>
              {' · '}
              <a href="https://creativecommons.org/licenses/by/3.0/deed.es" target="_blank" rel="noopener noreferrer" className="underline hover:text-white/60">CC BY 3.0</a>
            </p>
          </div>

          {heard && (
            <p className="mt-3 max-w-lg text-sm text-muted-foreground">
              Tú: <span className="italic">“{heard}”</span>
            </p>
          )}

          <div className="relative mt-3 w-full max-w-lg rounded-2xl bg-brand-50 px-5 py-4 text-left dark:bg-brand-950/40" aria-live="polite">
            <span className="absolute -top-2 left-1/2 h-4 w-4 -translate-x-1/2 rotate-45 bg-brand-50 dark:bg-brand-950/40" />
            <div className="relative flex items-start gap-3">
              <p className="flex-1 whitespace-pre-line text-lg leading-relaxed text-foreground">{bubble}</p>
              <button
                onClick={() => { speaker.unlock(); void speaker.speak(speakable(bubble)) }}
                aria-label="Escuchar otra vez"
                title="Escuchar otra vez"
                className="shrink-0 rounded-full p-1.5 text-brand-600 hover:bg-brand-100 dark:hover:bg-brand-900/40"
              >
                <Volume2 className="h-5 w-5" />
              </button>
            </div>
          </div>

          {/* Algo espera su "sí": dos botones grandes (o lo dice con la voz). */}
          {pending && !busy && (
            <div className="mt-4 w-full max-w-lg rounded-2xl border-2 border-amber-300 bg-amber-50 p-4 text-left dark:border-amber-700 dark:bg-amber-950/30">
              <p className="text-base font-semibold text-foreground">¿Lo hago?</p>
              <p className="mt-1 text-base text-foreground">{pending.summary}</p>
              <div className="mt-3 flex gap-3">
                <button
                  onClick={() => void answer(true)}
                  className="inline-flex flex-1 items-center justify-center gap-2 rounded-xl bg-brand-500 px-5 py-3.5 text-lg font-bold text-white hover:bg-brand-600"
                >
                  <Check className="h-5 w-5" /> Sí, hazlo
                </button>
                <button
                  onClick={() => void answer(false)}
                  className="inline-flex flex-1 items-center justify-center gap-2 rounded-xl border border-border px-5 py-3.5 text-lg text-foreground hover:bg-muted"
                >
                  <X className="h-5 w-5" /> No
                </button>
              </div>
            </div>
          )}

          {photo && (
            <div className="mt-4 flex items-center gap-3 rounded-2xl border border-border p-2 pr-3">
              <img src={photo.preview} alt="Foto del producto" className="h-16 w-16 rounded-xl object-cover" />
              <p className="text-sm text-muted-foreground">Foto lista: dime qué producto es.</p>
              <button onClick={clearPhoto} aria-label="Quitar la foto" className="rounded-full p-1.5 text-muted-foreground hover:bg-muted">
                <X className="h-4 w-4" />
              </button>
            </div>
          )}

          {step === 'recording' ? (
            <div className="mt-5 flex flex-col items-center">
              <button
                onClick={() => void stopRecording()}
                aria-label="Terminar de hablar"
                className="flex h-24 w-24 items-center justify-center rounded-full bg-rose-500 text-white shadow-xl transition-transform hover:bg-rose-600 active:scale-95"
              >
                <Square className="h-9 w-9" fill="currentColor" />
              </button>
              <p className="mt-2 text-base text-muted-foreground">
                {Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, '0')} · toca el botón rojo al terminar
              </p>
            </div>
          ) : micAvailable && !typing ? (
            <div className="mt-5 flex flex-col items-center">
              <div className="relative flex h-28 w-28 items-center justify-center">
                {!busy && <span className="absolute inset-2 animate-ping rounded-full bg-brand-500/20" />}
                <button
                  onClick={() => void startRecording()}
                  disabled={busy}
                  aria-label={pending ? 'Responder con la voz' : 'Tocar y hablar'}
                  className="relative flex h-24 w-24 items-center justify-center rounded-full bg-brand-500 text-white shadow-xl transition-transform hover:bg-brand-600 active:scale-95 disabled:opacity-50"
                >
                  <Mic className="h-10 w-10" />
                </button>
              </div>
              <p className="mt-1 text-lg font-semibold text-foreground">
                {step === 'processing' ? 'Pensando…' : pending ? 'O dímelo: “sí” o “no”' : 'Tocar y hablar'}
              </p>
              <div className="mt-1 flex flex-wrap justify-center gap-x-5 gap-y-1">
                <button onClick={() => setTyping(true)} className="inline-flex items-center gap-2 text-base text-muted-foreground hover:text-foreground">
                  <Keyboard className="h-5 w-5" /> ¿Prefieres escribir?
                </button>
                <button
                  onClick={() => photoInput.current?.click()}
                  disabled={busy}
                  className="inline-flex items-center gap-2 text-base text-muted-foreground hover:text-foreground disabled:opacity-50"
                >
                  <Camera className="h-5 w-5" /> {uploading ? 'Subiendo foto…' : 'Foto de un producto'}
                </button>
              </div>
            </div>
          ) : (
            <form
              className="mt-4 w-full max-w-lg text-left"
              onSubmit={(e) => { e.preventDefault(); void sendText(text) }}
            >
              <textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                rows={3}
                maxLength={2000}
                aria-label="Escribe lo que necesitas"
                placeholder="Ej. ¿Qué citas tengo mañana?"
                className="w-full rounded-xl border border-border bg-background p-3 text-base text-foreground placeholder:text-muted-foreground"
              />
              <div className="mt-2 flex flex-wrap gap-2">
                <button type="submit" disabled={busy || !text.trim()} className="rounded-xl bg-brand-500 px-5 py-3 text-base font-semibold text-white disabled:opacity-50">
                  Enviar
                </button>
                <button
                  type="button"
                  onClick={() => photoInput.current?.click()}
                  disabled={busy}
                  aria-label="Foto de un producto"
                  className="inline-flex items-center gap-2 rounded-xl border border-border px-4 py-3 text-base text-foreground hover:bg-muted disabled:opacity-50"
                >
                  <Camera className="h-5 w-5" /> {uploading ? 'Subiendo…' : 'Foto'}
                </button>
                {micAvailable && (
                  <button type="button" onClick={() => setTyping(false)} className="rounded-xl border border-border px-5 py-3 text-base text-foreground hover:bg-muted">
                    Mejor lo digo
                  </button>
                )}
              </div>
            </form>
          )}

          <input
            ref={photoInput}
            type="file"
            accept="image/jpeg,image/png,image/webp"
            capture="environment"
            className="hidden"
            onChange={(e) => void pickPhoto(e.target.files?.[0])}
          />

          {/* Para arrancar: ejemplos que se mandan con un toque */}
          {!history.length && !busy && (
            <div className="mt-5 flex flex-wrap justify-center gap-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => void sendText(s)}
                  className="rounded-full border border-border px-4 py-2 text-sm text-foreground hover:bg-muted"
                >
                  {s}
                </button>
              ))}
            </div>
          )}
        </div>

        {done.length > 0 && (
          <div className="rounded-2xl border border-border bg-card p-4">
            <p className="mb-2 text-sm font-semibold text-muted-foreground">Lo que hice</p>
            <ul className="space-y-1.5">
              {done.map((a, i) => (
                <li key={i} className="flex items-start gap-2 text-base text-foreground">
                  <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-emerald-500" /> {a.summary}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </>
  )
}
