import { useEffect, useRef, useState, lazy, Suspense } from 'react'
import { useLocation } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Camera, CheckCheck, Mic, Send, Square, Volume2, VolumeX, X } from 'lucide-react'
import api, { getApiError } from '@/lib/api'
import { useAuth } from '@/contexts/AuthContext'
import { useCopilot, type CopilotAction, type PendingConfirmation } from '@/contexts/CopilotContext'
import MascotSmart from '@/components/MascotSmart'
import BubbleTail from '@/components/BubbleTail'
import { chatPalette, wallpaperPattern } from '@/lib/chatLook'
import { canRecordVoice, micErrorMessage, startVoiceRecording, type VoiceSession } from '@/lib/voiceRecorder'
import { useSpeaker } from '@/lib/useSpeaker'

// three.js solo se baja cuando el dueño usa la voz.
const Mascot3D = lazy(() => import('@/components/Mascot3D'))

// El asistente del dueño flotando en todo el panel, con la cara del chat de
// /sitio/iaradio pero conectado al Copiloto: lee Y escribe datos (productos,
// horario, cupones, campañas, citas). Todo cambio espera su "Sí, hazlo" firmado
// por el backend (copilot_service.py). Comparte el hilo con /app/copilot.
const GREEN = '#25D366'
const PAL = chatPalette(GREEN, true)
const BG = '#0b0d16'
const BORDER = 'rgba(255,255,255,0.09)'
const HIDDEN_ON = ['/app/copilot']
const MAX_SECONDS = 120

const QUICK_ASKS = [
  { icon: '✨', label: '¿Mi bot ya está listo?', text: '¿Mi bot ya está listo? ¿Qué le falta?' },
  { icon: '🧪', label: 'Prueba mi bot', text: 'Prueba mi bot: ¿qué horario tienen?' },
  { icon: '➕', label: 'Agregar un producto', text: 'Quiero agregar un producto' },
  { icon: '🕒', label: 'Cambiar mi horario', text: 'Quiero cambiar mi horario' },
]

interface ChatResponse {
  reply: string
  actions: CopilotAction[]
  pending_confirmation: PendingConfirmation | null
  transcript?: string
}

/** Lo que se dice en voz alta: sin marcas de formato y no muy largo. */
function speakable(text: string): string {
  return text.replace(/[*_#`>]/g, '').replace(/^\s*[-•]\s*/gm, '').replace(/\s+/g, ' ').trim().slice(0, 600)
}

export default function OwnerAssistant() {
  const { pathname } = useLocation()
  const { user, setUser } = useAuth()
  const qc = useQueryClient()
  const { messages, setMessages, pendingConfirmation, setPendingConfirmation, assistantOpen: open, setAssistantOpen: setOpen, setPageBuilderOpen } = useCopilot()
  const [input, setInput] = useState('')
  const [recording, setRecording] = useState(false)
  const [seconds, setSeconds] = useState(0)
  // Foto de un producto (botón de cámara): viaja con lo siguiente que diga el dueño.
  const [photo, setPhoto] = useState<{ url: string; preview: string } | null>(null)
  const [uploading, setUploading] = useState(false)
  const endRef = useRef<HTMLDivElement>(null)
  const photoInput = useRef<HTMLInputElement>(null)
  const session = useRef<VoiceSession | null>(null)
  const timer = useRef<ReturnType<typeof setInterval> | null>(null)
  const speaker = useSpeaker({ robot: true })
  const micAvailable = canRecordVoice()
  // Al usar el micrófono sale la mascota 3D grande (como en el chat de voz) hasta cerrar.
  const [voiceMode, setVoiceMode] = useState(false)

  const chat = useMutation({
    mutationFn: (payload: { message: string; history: { role: string; content: string }[] }) =>
      api.post<ChatResponse>('/copilot/chat', payload, { timeout: 45000 }).then((r) => r.data),
  })
  const confirm = useMutation({
    mutationFn: (payload: { confirmation_id: string; approve: boolean }) =>
      api.post<ChatResponse>('/copilot/confirm', payload).then((r) => r.data),
  })
  const voice = useMutation({
    mutationFn: (form: FormData) => api.post<ChatResponse>('/copilot/voice', form, { timeout: 60000 }).then((r) => r.data),
  })
  const busy = chat.isPending || confirm.isPending || voice.isPending || uploading
  const mood = recording ? 'listening' : busy ? 'thinking' : speaker.speaking ? 'speaking' : 'idle'

  useEffect(() => {
    const box = endRef.current?.closest('.overflow-y-auto')
    if (box) box.scrollTop = box.scrollHeight
  }, [messages, pendingConfirmation, busy, open])

  useEffect(() => () => {
    session.current?.cancel()
    if (timer.current) clearInterval(timer.current)
  }, [])

  // Tope de 2 minutos: se corta solo y se manda lo grabado.
  useEffect(() => {
    if (recording && seconds >= MAX_SECONDS) void stopRecording()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recording, seconds])

  if (HIDDEN_ON.some((p) => pathname.startsWith(p))) return null

  const addAssistant = (content: string, extra: { actions?: CopilotAction[]; isError?: boolean } = {}) =>
    setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: 'assistant', content, ...extra }])

  const onReply = (data: ChatResponse) => {
    addAssistant(data.reply, { actions: data.actions })
    setPendingConfirmation(data.pending_confirmation ?? null)
    // "Arma mi página": se abre el armador guiado (el mismo del panel) y el chat se aparta.
    if (data.actions?.some((a) => a.tool === 'open_page_builder' && !(a.data as { has_page?: boolean } | undefined)?.has_page)) {
      speaker.stop()
      setVoiceMode(false)
      setOpen(false)
      setPageBuilderOpen(true)
    }
    // Si algo se guardó, que lo que ya está en pantalla (catálogo, horario…) se actualice.
    if (data.actions?.length) {
      void qc.invalidateQueries()
      api.get('/me').then((r) => setUser(r.data)).catch(() => {})
    }
  }

  const historyNow = () => messages.filter((m) => m.content).map(({ role, content }) => ({ role, content }))

  const clearPhoto = () => {
    if (photo) URL.revokeObjectURL(photo.preview)
    setPhoto(null)
  }

  // Por el camino de voz van: lo grabado, y lo escrito cuando trae foto.
  const sendVoice = (form: FormData, opts: { userText?: string; speak: boolean }) => {
    const history = historyNow()
    if (history.length) form.append('history', JSON.stringify(history))
    if (pendingConfirmation) form.append('confirmation_id', pendingConfirmation.confirmation_id)
    if (photo) form.append('photo_url', photo.url)
    if (opts.userText) setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: 'user', content: opts.userText! }])
    voice.mutate(form, {
      onSuccess: (data) => {
        if (!opts.userText && data.transcript) {
          setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: 'user', content: data.transcript! }])
        }
        onReply(data)
        clearPhoto()
        if (opts.speak) void speaker.speak(speakable(data.reply))
      },
      onError: (err) => addAssistant(getApiError(err, 'No te entendí bien. ¿Me lo repites?'), { isError: true }),
    })
  }

  const send = (text?: string) => {
    const value = (text ?? input).trim()
    if (!value || busy || pendingConfirmation) return
    speaker.unlock()
    setInput('')
    if (photo) {
      const form = new FormData()
      form.append('text', value)
      sendVoice(form, { userText: value, speak: false })
      return
    }
    const history = historyNow()
    setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: 'user', content: value }])
    chat.mutate(
      { message: value, history },
      { onSuccess: onReply, onError: (err) => addAssistant(getApiError(err, 'No se pudo procesar tu mensaje. Intenta de nuevo.'), { isError: true }) },
    )
  }

  const startRecording = async () => {
    if (busy || recording) return
    speaker.unlock() // dentro del toque: iPhone deja hablar a la mascota después
    speaker.stop()
    try {
      session.current = await startVoiceRecording()
    } catch (err) {
      addAssistant(micErrorMessage(err), { isError: true })
      return
    }
    setSeconds(0)
    setVoiceMode(true)
    setRecording(true)
    timer.current = setInterval(() => setSeconds((s) => s + 1), 1000)
  }

  async function stopRecording() {
    if (timer.current) clearInterval(timer.current)
    setRecording(false)
    const s = session.current
    session.current = null
    if (!s) return
    const rec = await s.stop()
    if (rec.seconds < 1) {
      addAssistant('No alcancé a oírte. Toca el micrófono y dime qué necesitas.', { isError: true })
      return
    }
    const form = new FormData()
    const ext = rec.mimeType.includes('mp4') ? 'mp4' : rec.mimeType.includes('ogg') ? 'ogg' : 'webm'
    form.append('audio', rec.blob, `orden.${ext}`)
    sendVoice(form, { speak: true })
  }

  const pickPhoto = async (file: File | undefined) => {
    if (!file) return
    setUploading(true)
    try {
      const form = new FormData()
      form.append('file', file)
      const { data } = await api.post<{ url: string }>('/copilot/photo', form)
      clearPhoto()
      setPhoto({ url: data.url, preview: URL.createObjectURL(file) })
    } catch (err) {
      addAssistant(getApiError(err, 'No se pudo subir la foto. Intenta de nuevo.'), { isError: true })
    } finally {
      setUploading(false)
      if (photoInput.current) photoInput.current.value = ''
    }
  }

  const decide = (approve: boolean) => {
    if (!pendingConfirmation || busy) return
    confirm.mutate(
      { confirmation_id: pendingConfirmation.confirmation_id, approve },
      {
        onSuccess: onReply,
        onError: (err) => {
          addAssistant(getApiError(err, 'No se pudo procesar la confirmación. Intenta de nuevo.'), { isError: true })
          setPendingConfirmation(null)
        },
      },
    )
  }

  const shown = messages.filter((m) => m.content)

  return (
    <>
      {open && (
        <div className="fixed inset-0 z-[90] flex items-center justify-center p-4" onClick={() => { speaker.stop(); setVoiceMode(false); setOpen(false) }}>
          <div className="anim-backdrop absolute inset-0 bg-black/50" aria-hidden />
          <div
            className="anim-sheet relative flex h-[min(40rem,85dvh)] w-full max-w-md flex-col overflow-hidden rounded-3xl shadow-2xl"
            style={{ background: BG, color: '#fff', border: `1px solid ${BORDER}` }}
            role="dialog"
            aria-modal="true"
            aria-label="Asistente IaRadio"
            onClick={(e) => e.stopPropagation()}
          >
          <div className="flex items-center justify-between px-3 py-2 shadow-sm" style={{ background: GREEN, color: PAL.onBrand }}>
            <div className="flex min-w-0 items-center gap-2">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-full bg-white/95">
                <MascotSmart mood={mood} size={40} color={GREEN} />
              </div>
              <div className="min-w-0">
                <p className="truncate text-[16px] font-semibold leading-tight">IaRadio</p>
                <p className="truncate text-xs leading-tight opacity-80">
                  {recording ? 'te escucho…' : busy ? 'escribiendo…' : 'tu asistente · en línea'}
                </p>
              </div>
            </div>
            <div className="flex items-center">
              {micAvailable && (
                <button
                  onClick={() => speaker.setMuted(!speaker.muted)}
                  aria-label={speaker.muted ? 'Activar la voz' : 'Silenciar la voz'}
                  className="rounded-full p-2 opacity-90"
                >
                  {speaker.muted ? <VolumeX size={20} /> : <Volume2 size={20} />}
                </button>
              )}
              <button onClick={() => { speaker.stop(); setVoiceMode(false); setOpen(false) }} aria-label="Cerrar asistente" className="rounded-full p-2 opacity-90">
                <X size={20} />
              </button>
            </div>
          </div>

          {voiceMode && (
            <div
              className="flex shrink-0 flex-col items-center pb-1 pt-1"
              style={{ background: `color-mix(in srgb, ${GREEN} 22%, #0a0f2e)` }}
            >
              <Suspense fallback={<div style={{ height: 150 }} />}>
                <Mascot3D mood={mood} getLevel={speaker.level} size={130} color={GREEN} />
              </Suspense>
            </div>
          )}

          <div
            className="custom-scrollbar flex-1 overflow-y-auto overscroll-contain px-3 py-3"
            style={{ background: PAL.wallpaper, backgroundImage: wallpaperPattern(PAL.doodle), backgroundSize: '160px 160px' }}
          >
            {!shown.length && (
              <div className="mx-auto mt-2 w-full text-center">
                <p className="mx-auto w-fit rounded-lg px-3 py-1.5 text-sm shadow-sm" style={{ background: PAL.incoming, color: PAL.text }}>
                  ¡Hola{user?.business_name ? `, ${user.business_name}` : ''}! Dime qué necesitas: reviso y pruebo tu bot, agrego productos,
                  cambio tu horario, creo cupones… Antes de guardar algo, te pregunto.
                </p>
                <div className="mt-3 grid grid-cols-2 gap-2">
                  {QUICK_ASKS.map((q) => (
                    <button
                      key={q.label}
                      type="button"
                      onClick={() => send(q.text)}
                      disabled={busy}
                      className="flex flex-col items-center gap-1 rounded-2xl border border-white/10 bg-[#151926] px-2 py-3 text-sm font-semibold transition-colors hover:border-[#25D366] disabled:opacity-50"
                      style={{ color: GREEN }}
                    >
                      <span className="text-xl">{q.icon}</span>
                      {q.label}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {shown.map((msg, i) => {
              const mine = msg.role === 'user'
              const first = i === 0 || shown[i - 1].role !== msg.role
              const fill = mine ? PAL.outgoing : PAL.incoming
              return (
                <div key={msg.id} className={`flex ${mine ? 'justify-end' : 'justify-start'} ${first ? 'mt-2.5' : 'mt-0.5'}`}>
                  <div className={`flex max-w-[85%] flex-col gap-1.5 ${mine ? 'items-end' : 'items-start'}`}>
                    <div
                      className="relative rounded-lg px-2.5 py-1.5 text-[15px] leading-snug shadow-sm"
                      style={{
                        background: msg.isError ? '#4a1d1d' : fill,
                        color: PAL.text,
                        ...(first ? (mine ? { borderTopRightRadius: 0 } : { borderTopLeftRadius: 0 }) : {}),
                      }}
                    >
                      {first && <BubbleTail side={mine ? 'right' : 'left'} fill={msg.isError ? '#4a1d1d' : fill} />}
                      <span className="whitespace-pre-line break-words">{msg.content}</span>
                      {mine && <CheckCheck size={15} className="float-right ml-2 mt-1.5" style={{ color: PAL.ticks }} aria-label="Enviado" />}
                    </div>
                    {!mine && !msg.isError && msg.actions?.map((a, k) => (
                      <div
                        key={k}
                        className="w-full rounded-2xl border border-white/10 bg-[#151926] px-3 py-2 text-xs"
                        style={{ color: PAL.text }}
                      >
                        ✅ {a.summary}
                      </div>
                    ))}
                  </div>
                </div>
              )
            })}

            {pendingConfirmation && (
              <div className="mt-3 rounded-2xl border border-[#25D366]/40 bg-[#151926] p-3">
                <p className="text-xs font-semibold uppercase tracking-wide" style={{ color: GREEN }}>¿Lo hago?</p>
                <p className="mt-1 text-sm" style={{ color: PAL.text }}>{pendingConfirmation.summary}</p>
                <div className="mt-3 grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => decide(true)}
                    disabled={busy}
                    className="rounded-xl py-2.5 text-sm font-semibold disabled:opacity-50"
                    style={{ background: GREEN, color: PAL.onBrand }}
                  >
                    Sí, hazlo
                  </button>
                  <button
                    type="button"
                    onClick={() => decide(false)}
                    disabled={busy}
                    className="rounded-xl border border-white/15 py-2.5 text-sm font-semibold text-white disabled:opacity-50"
                  >
                    Cancelar
                  </button>
                </div>
              </div>
            )}

            {busy && (
              <div className="mt-2.5 flex justify-start">
                <div
                  className="relative flex items-center gap-1 rounded-lg px-3.5 py-3 shadow-sm"
                  style={{ background: PAL.incoming, borderTopLeftRadius: 0 }}
                  aria-label="Escribiendo…"
                >
                  <BubbleTail side="left" fill={PAL.incoming} />
                  {[0, 1, 2].map((d) => (
                    <span key={d} className="typing-dot h-2 w-2 rounded-full" style={{ background: PAL.meta, animationDelay: `${d * 160}ms` }} />
                  ))}
                </div>
              </div>
            )}
            <div ref={endRef} />
          </div>

          {photo && (
            <div className="flex items-center gap-3 px-3 py-2" style={{ background: PAL.bar }}>
              <img src={photo.preview} alt="Foto del producto" className="h-12 w-12 rounded-lg object-cover" />
              <p className="flex-1 text-sm" style={{ color: PAL.text }}>Foto lista: dime qué producto es.</p>
              <button type="button" onClick={clearPhoto} aria-label="Quitar la foto" className="rounded-full p-1.5 opacity-80">
                <X size={16} />
              </button>
            </div>
          )}

          <form
            onSubmit={(e) => {
              e.preventDefault()
              send()
            }}
            className="flex items-center gap-1.5 px-2 py-2"
            style={{ background: PAL.bar }}
          >
            <button
              type="button"
              onClick={() => photoInput.current?.click()}
              disabled={busy || recording}
              aria-label="Foto de un producto"
              className="flex h-12 w-10 shrink-0 items-center justify-center rounded-full opacity-80 disabled:opacity-40"
              style={{ color: PAL.text }}
            >
              <Camera size={21} />
            </button>
            <input
              ref={photoInput}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              capture="environment"
              className="hidden"
              onChange={(e) => void pickPhoto(e.target.files?.[0])}
            />
            {recording ? (
              <p className="min-w-0 flex-1 px-3 text-base" style={{ color: PAL.text }} aria-live="polite">
                🔴 {Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, '0')} · toca el cuadro al terminar
              </p>
            ) : (
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder={pendingConfirmation ? 'Responde con los botones o con la voz' : 'Mensaje'}
                disabled={busy || !!pendingConfirmation}
                aria-label="Escribe lo que necesitas"
                enterKeyHint="send"
                className="min-w-0 flex-1 rounded-full px-4 py-3 text-base outline-none placeholder:text-white/40 disabled:opacity-50"
                style={{ background: PAL.field, color: PAL.text }}
              />
            )}
            {recording ? (
              <button
                type="button"
                onClick={() => void stopRecording()}
                aria-label="Terminar de hablar"
                className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-rose-500 text-white shadow-sm active:scale-95"
              >
                <Square size={18} fill="currentColor" />
              </button>
            ) : micAvailable && !input.trim() ? (
              <button
                type="button"
                onClick={() => void startRecording()}
                disabled={busy}
                aria-label={pendingConfirmation ? 'Responder con la voz' : 'Tocar y hablar'}
                className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full shadow-sm transition-transform active:scale-95 disabled:opacity-50"
                style={{ background: GREEN, color: PAL.onBrand }}
              >
                <Mic size={20} />
              </button>
            ) : (
              <button
                type="submit"
                disabled={busy || !!pendingConfirmation || !input.trim()}
                aria-label="Enviar"
                className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full shadow-sm transition-transform active:scale-95 disabled:opacity-50"
                style={{ background: GREEN, color: PAL.onBrand }}
              >
                <Send size={19} />
              </button>
            )}
          </form>
          </div>
        </div>
      )}

      {/* Cuelga de un hilo arriba a la derecha y se mece; al pasar el mouse se detiene. */}
      {!open && (
        <button
          type="button"
          onClick={() => setOpen(true)}
          aria-label="Abrir asistente IaRadio"
          className="swing-hang fixed right-6 top-0 z-40 flex flex-col items-center"
        >
          <span className="h-6 w-px bg-white/40" aria-hidden />
          <span
            className="flex h-16 w-16 items-center justify-center rounded-full bg-white shadow-xl"
            style={{ boxShadow: `0 0 0 3px ${GREEN}, 0 12px 32px ${GREEN}66` }}
          >
            <MascotSmart mood="happy" size={56} color={GREEN} />
          </span>
        </button>
      )}
    </>
  )
}
