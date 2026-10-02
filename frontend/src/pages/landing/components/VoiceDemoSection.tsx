import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import api, { getApiError } from '@/lib/api'
import BotFace, { type FaceMood } from '@/components/BotFace'
import { canRecordVoice, micErrorMessage, startVoiceRecording, type VoiceSession } from '@/lib/voiceRecorder'
import { useSpeaker } from '@/lib/useSpeaker'
import { saveDemoDraft } from '@/lib/demoDraft'
import { ArrowRight, Check, Keyboard, Mic, RotateCcw, SkipForward, Square, Volume2, VolumeX } from 'lucide-react'

// "Pruébalo en 30 segundos": un visitante SIN cuenta le cuenta su negocio a
// la carita y ve cómo contestaría SU bot, con sus precios y su horario.
// Backend: api/v1/voice_demo.py (público, con límites; nada se guarda allá).
// Lo dictado se guarda en el navegador (demoDraft) y se recupera al registrarse.

interface SignedLine {
  text: string
  sig: string
}

interface DemoQuestion extends SignedLine {
  field: string
}

interface DemoResult {
  profile: unknown
  say: SignedLine
  pending_questions: DemoQuestion[]
  spoken_summary: SignedLine
  demo_chat: { from: 'cliente' | 'bot'; text: string }[]
  closing: SignedLine
}

type Step = 'intro' | 'recording' | 'processing' | 'asking' | 'result'

const MAX_SECONDS = 60
const GREETING_FALLBACK =
  '¡Hola! ¿Tienes un negocio? Cuéntame de él: qué vendes, tus precios y tu horario, y te enseño cómo contestaría tu bot.'

export default function VoiceDemoSection() {
  const [step, setStep] = useState<Step>('intro')
  const [result, setResult] = useState<DemoResult | null>(null)
  const [greeting, setGreeting] = useState<SignedLine>({ text: GREETING_FALLBACK, sig: '' })
  const [bubble, setBubble] = useState<SignedLine>({ text: GREETING_FALLBACK, sig: '' })
  const [questions, setQuestions] = useState<DemoQuestion[]>([])
  const [asked, setAsked] = useState<string[]>([])
  const [error, setError] = useState(false)
  const [typing, setTyping] = useState(false)
  const [text, setText] = useState('')
  const [seconds, setSeconds] = useState(0)
  const [volume, setVolume] = useState(0)
  const session = useRef<VoiceSession | null>(null)
  const timer = useRef<ReturnType<typeof setInterval> | null>(null)
  const speaker = useSpeaker({ publicDemo: true })
  const micAvailable = canRecordVoice()
  const question = questions[0] ?? null

  useEffect(() => {
    api.get('/public/voice-demo/hello')
      .then(({ data }) => {
        setGreeting(data.greeting)
        setBubble((b) => (b.text === GREETING_FALLBACK ? data.greeting : b))
      })
      .catch(() => {})
    return () => {
      session.current?.cancel()
      if (timer.current) clearInterval(timer.current)
    }
  }, [])

  const say = (line: SignedLine) => {
    setBubble(line)
    void speaker.speak(line.text, line.sig)
  }

  const mood: FaceMood =
    step === 'recording' ? 'listening'
      : step === 'processing' ? 'thinking'
        : error ? 'confused'
          : speaker.speaking ? 'speaking'
            : step === 'result' ? 'happy'
              : 'idle'

  const send = async (form: FormData) => {
    setStep('processing')
    setError(false)
    setBubble({ text: 'Déjame ordenar lo que me contaste…', sig: '' })
    if (result) form.append('draft', JSON.stringify(result.profile))
    const nowAsked = question && !asked.includes(question.field) ? [...asked, question.field] : asked
    if (question) form.append('question', question.field)
    if (nowAsked.length) form.append('asked', nowAsked.join(','))
    try {
      const { data } = await api.post<DemoResult>('/public/voice-demo/listen', form)
      setResult(data)
      setAsked(nowAsked)
      setQuestions(data.pending_questions)
      setTyping(false)
      setText('')
      saveDemoDraft(data.profile)
      if (data.pending_questions.length) {
        setStep('asking')
        say(data.say)
      } else {
        setStep('result')
        say(data.demo_chat.length ? data.closing : data.say)
      }
    } catch (err) {
      setError(true)
      setBubble({ text: getApiError(err, 'Uy, no te alcancé a entender. ¿Lo intentamos otra vez?'), sig: '' })
      setStep(result ? (question ? 'asking' : 'result') : 'intro')
    }
  }

  const stopRecording = async () => {
    if (timer.current) clearInterval(timer.current)
    const s = session.current
    session.current = null
    if (!s) return
    const rec = await s.stop()
    if (rec.seconds < 2) {
      setError(true)
      setBubble({ text: 'Fue muy cortito. Toca el micrófono y cuéntame un poco más.', sig: '' })
      setStep(result ? 'asking' : 'intro')
      return
    }
    const form = new FormData()
    const ext = rec.mimeType.includes('mp4') ? 'mp4' : rec.mimeType.includes('ogg') ? 'ogg' : 'webm'
    form.append('audio', rec.blob, `nota.${ext}`)
    await send(form)
  }

  const startRecording = async () => {
    speaker.unlock()
    speaker.stop()
    setError(false)
    try {
      session.current = await startVoiceRecording(setVolume)
    } catch (err) {
      setError(true)
      setBubble({ text: micErrorMessage(err), sig: '' })
      setTyping(true)
      return
    }
    setSeconds(0)
    setBubble({ text: question ? `Te escucho… ${question.text}` : 'Te escucho… cuéntame de tu negocio.', sig: '' })
    setStep('recording')
    timer.current = setInterval(() => setSeconds((s) => s + 1), 1000)
  }

  useEffect(() => {
    if (step === 'recording' && seconds >= MAX_SECONDS) void stopRecording()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, seconds])

  const sendText = async () => {
    speaker.unlock()
    if (!text.trim()) return
    const form = new FormData()
    form.append('text', text)
    await send(form)
  }

  const skip = () => {
    speaker.unlock()
    if (!question) return
    setAsked((a) => [...a, question.field])
    const rest = questions.slice(1)
    setQuestions(rest)
    setTyping(false)
    if (rest.length) say(rest[0])
    else showResult()
  }

  const showResult = () => {
    speaker.unlock()
    setQuestions([])
    setTyping(false)
    setStep('result')
    if (result) say(result.demo_chat.length ? result.closing : result.say)
  }

  const restart = () => {
    speaker.stop()
    setResult(null)
    setQuestions([])
    setAsked([])
    setError(false)
    setTyping(false)
    setStep('intro')
    setBubble(greeting)
  }

  return (
    <section id="pruebalo" className="relative px-5 py-20 scroll-mt-20">
      <div className="mx-auto max-w-5xl">
        <div className="mb-10 text-center">
          <p className="mb-3 text-sm font-semibold uppercase tracking-widest text-indigo-400">Pruébalo en 30 segundos</p>
          <h2 className="text-4xl font-black text-white sm:text-5xl">Cuéntale de tu negocio. Mira cómo contestaría tu bot.</h2>
          <p className="mt-4 text-lg text-gray-400">Sin registrarte. Solo habla, como en una nota de voz.</p>
        </div>

        <div className={`grid items-start gap-6 ${step === 'result' && result?.demo_chat.length ? 'lg:grid-cols-2' : ''}`}>
          {/* La carita */}
          <div className="glass relative mx-auto flex w-full max-w-xl flex-col items-center rounded-3xl px-5 pb-7 pt-5 text-center">
            <button
              onClick={() => speaker.setMuted(!speaker.muted)}
              aria-label={speaker.muted ? 'Activar la voz' : 'Silenciar la voz'}
              className="absolute right-4 top-4 rounded-full p-2 text-gray-400 hover:bg-white/10 hover:text-white"
            >
              {speaker.muted ? <VolumeX className="h-5 w-5" /> : <Volume2 className="h-5 w-5" />}
            </button>
            <BotFace mood={mood} volume={volume} size={150} />
            <div className="relative mt-3 w-full rounded-2xl bg-white/10 px-5 py-4 text-left" aria-live="polite">
              <span className="absolute -top-2 left-1/2 h-4 w-4 -translate-x-1/2 rotate-45 bg-white/10" />
              <div className="relative flex items-start gap-3">
                <p className="flex-1 text-lg leading-relaxed text-white">{bubble.text}</p>
                <button
                  onClick={() => { speaker.unlock(); void speaker.speak(bubble.text, bubble.sig || undefined) }}
                  aria-label="Escuchar otra vez"
                  className="shrink-0 rounded-full p-1.5 text-indigo-300 hover:bg-white/10"
                >
                  <Volume2 className="h-5 w-5" />
                </button>
              </div>
            </div>

            {(step === 'intro' || step === 'asking') && !typing && (
              <DemoMic
                label={step === 'asking' ? 'Tocar y responder' : 'Tocar y hablar'}
                available={micAvailable}
                onClick={startRecording}
                onType={() => setTyping(true)}
              />
            )}

            {step === 'asking' && !typing && (
              <div className="mt-3 flex flex-wrap justify-center gap-2">
                <button onClick={skip} className="inline-flex items-center gap-1.5 rounded-xl border border-white/15 px-4 py-2.5 text-base text-gray-200 hover:bg-white/10">
                  <SkipForward className="h-4 w-4" /> Saltar
                </button>
                <button onClick={showResult} className="inline-flex items-center gap-1.5 rounded-xl border border-white/15 px-4 py-2.5 text-base text-gray-200 hover:bg-white/10">
                  <Check className="h-4 w-4" /> Ya, enséñame
                </button>
              </div>
            )}

            {step === 'recording' && (
              <div className="mt-5 flex flex-col items-center">
                <button
                  onClick={stopRecording}
                  aria-label="Terminar de grabar"
                  className="flex h-20 w-20 items-center justify-center rounded-full bg-rose-500 text-white shadow-xl transition-transform hover:bg-rose-600 active:scale-95"
                >
                  <Square className="h-8 w-8" fill="currentColor" />
                </button>
                <p className="mt-2 text-base text-gray-300">0:{String(seconds).padStart(2, '0')} · toca el botón rojo al terminar</p>
              </div>
            )}

            {typing && step !== 'processing' && step !== 'result' && (
              <div className="mt-4 w-full text-left">
                <textarea
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  rows={4}
                  maxLength={1500}
                  aria-label={question ? question.text : 'Cuéntame de tu negocio'}
                  placeholder={question ? 'Escribe tu respuesta…' : 'Ej. Tengo una taquería, el taco de pastor cuesta 15, abrimos de lunes a sábado de 9 a 7…'}
                  className="w-full rounded-xl border border-white/15 bg-black/30 p-3 text-base text-white placeholder:text-gray-500"
                />
                <div className="mt-2 flex flex-wrap gap-2">
                  <button onClick={sendText} disabled={!text.trim()} className="rounded-xl bg-gradient-to-r from-[#674CC4] to-[#6366F1] px-5 py-3 text-base font-bold text-white disabled:opacity-50">
                    {question ? 'Responder' : 'Enséñame mi bot'}
                  </button>
                  {micAvailable && (
                    <button onClick={() => setTyping(false)} className="rounded-xl border border-white/15 px-5 py-3 text-base text-gray-200 hover:bg-white/10">
                      Mejor lo digo
                    </button>
                  )}
                </div>
              </div>
            )}

            {step === 'result' && (
              <div className="mt-5 flex w-full flex-col gap-2 sm:flex-row sm:justify-center">
                <Link
                  to="/register"
                  className="inline-flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-[#674CC4] to-[#6366F1] px-6 py-3.5 text-base font-black text-white shadow-xl shadow-[#674CC4]/30 transition-transform hover:scale-[1.03]"
                >
                  Crea tu cuenta y quédatelo <ArrowRight className="h-4 w-4" />
                </Link>
                <button onClick={restart} className="inline-flex items-center justify-center gap-2 rounded-xl border border-white/15 px-5 py-3.5 text-base text-gray-200 hover:bg-white/10">
                  <RotateCcw className="h-4 w-4" /> Empezar de nuevo
                </button>
              </div>
            )}
          </div>

          {/* "Así contestaría tu bot" */}
          {step === 'result' && result && result.demo_chat.length > 0 && <DemoChat chat={result.demo_chat} />}
        </div>
      </div>
    </section>
  )
}

function DemoMic({ label, available, onClick, onType }: { label: string; available: boolean; onClick: () => void; onType: () => void }) {
  if (!available) {
    return (
      <button onClick={onType} className="mt-5 rounded-xl bg-gradient-to-r from-[#674CC4] to-[#6366F1] px-5 py-3 text-base font-bold text-white">
        Escríbelo aquí
      </button>
    )
  }
  return (
    <div className="mt-5 flex flex-col items-center">
      <div className="relative flex h-24 w-24 items-center justify-center">
        <span className="absolute inset-2 animate-ping rounded-full bg-indigo-500/25" />
        <button
          onClick={onClick}
          aria-label={label}
          className="relative flex h-20 w-20 items-center justify-center rounded-full bg-gradient-to-br from-[#818cf8] to-[#6d28d9] text-white shadow-xl shadow-indigo-500/30 transition-transform active:scale-95"
        >
          <Mic className="h-9 w-9" />
        </button>
      </div>
      <p className="mt-2 text-lg font-semibold text-white">{label}</p>
      <button onClick={onType} className="mt-1 inline-flex items-center gap-2 text-base text-gray-400 hover:text-white">
        <Keyboard className="h-5 w-5" /> ¿Prefieres escribir?
      </button>
    </div>
  )
}

function DemoChat({ chat }: { chat: { from: 'cliente' | 'bot'; text: string }[] }) {
  return (
    <div className="mx-auto w-full max-w-md overflow-hidden rounded-3xl border border-white/10 bg-[#0b141a] shadow-2xl">
      <div className="flex items-center gap-3 bg-[#202c33] px-4 py-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-br from-[#818cf8] to-[#6d28d9] text-sm font-bold text-white">TU</div>
        <div>
          <p className="text-sm font-semibold text-white">Así contestaría tu bot</p>
          <p className="text-xs text-emerald-400">en línea · responde al instante</p>
        </div>
      </div>
      <ul className="space-y-2 px-3 py-4">
        {chat.map((m, i) => (
          <li key={i} className={`flex ${m.from === 'cliente' ? 'justify-end' : 'justify-start'}`}>
            <p
              className={`max-w-[85%] rounded-xl px-3 py-2 text-[15px] leading-snug text-white ${
                m.from === 'cliente' ? 'rounded-br-sm bg-[#005c4b]' : 'rounded-bl-sm bg-[#202c33]'
              }`}
            >
              {m.text}
            </p>
          </li>
        ))}
      </ul>
    </div>
  )
}
