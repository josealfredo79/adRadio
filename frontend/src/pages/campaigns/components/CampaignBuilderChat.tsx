import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Loader2, Mic, Send, Square } from 'lucide-react'
import api, { getApiError } from '@/lib/api'
import { canRecordVoice, micErrorMessage, startVoiceRecording, type VoiceSession } from '@/lib/voiceRecorder'

// La campaña que pregunta (docs/specs/2026-10-29-campana-que-pregunta.md): el
// bot pregunta una cosa a la vez con botones. La lógica vive en el backend
// (app/domain/campaign_builder.py); aquí solo se dibuja. La usan Campañas y el
// Copiloto web.

export interface BuilderChoice { id: string; label: string; locked: boolean }
export interface BuilderPreview { kind: 'text' | 'image' | 'audio'; text: string; image_url: string | null; audio_url: string | null }
export interface BuilderStep {
  campaign_id: string | null
  step: string
  text: string
  choices: BuilderChoice[]
  input: 'what' | 'edit' | 'contact' | 'photo' | null
  preview: BuilderPreview | null
  done: boolean
}

interface Bubble { from: 'bot' | 'me'; text: string; preview?: BuilderPreview | null }

// Lo que tarda: grabar una cuña o dibujar una foto toma unos segundos.
function waitText(step: string, choice?: string): string {
  if (step === 'style' || (choice === 'other' && step === 'preview')) return 'Grabando tu cuña…'
  if (step === 'photo') return 'Armando tu imagen…'
  if (step === 'what' || step === 'format') return 'Armando tu promo…'
  return 'Un momento…'
}

const PLACEHOLDER: Record<string, string> = {
  what: 'Ej. 2x1 en micas este viernes',
  edit: 'Escribe cómo quieres que diga',
  contact: 'Nombre o teléfono',
}

export function CampaignBuilderChat({ initial, onDone }: { initial?: BuilderStep; onDone?: () => void }) {
  const qc = useQueryClient()
  const [bubbles, setBubbles] = useState<Bubble[]>(initial ? [{ from: 'bot', text: initial.text, preview: initial.preview }] : [])
  const [step, setStep] = useState<BuilderStep | null>(initial ?? null)
  const [busy, setBusy] = useState<string | null>(initial ? null : 'Un momento…')
  const [error, setError] = useState('')
  const [draft, setDraft] = useState('')
  const [recording, setRecording] = useState(false)
  const recorder = useRef<VoiceSession | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const endRef = useRef<HTMLDivElement>(null)

  // campaignId null: empezar otra o retomar (el backend decide cuál).
  const turn = async (body: { choice?: string; text?: string }, said?: string, campaignId = step?.campaign_id ?? null) => {
    const wait = waitText(step?.step ?? 'what', body.choice)
    if (said) setBubbles((b) => [...b, { from: 'me', text: said }])
    setBusy(wait)
    setError('')
    try {
      const { data } = await api.post<BuilderStep>('/campaigns/builder', { campaign_id: campaignId, ...body })
      setStep(data)
      setBubbles((b) => [...b, { from: 'bot', text: data.text, preview: data.preview }])
      if (data.done) {
        qc.invalidateQueries({ queryKey: ['campaigns'] })
        qc.invalidateQueries({ queryKey: ['campaign-quota'] })
        onDone?.()
      }
    } catch (err) {
      setError(getApiError(err, 'No se pudo. Intenta de nuevo.'))
    } finally {
      setBusy(null)
    }
  }

  // Abrir: retoma la que quedó a medias o pregunta qué anunciar.
  useEffect(() => {
    if (initial) return
    let alive = true
    api.post<BuilderStep>('/campaigns/builder', {}).then(({ data }) => {
      if (!alive) return
      setStep(data)
      setBubbles([{ from: 'bot', text: data.text, preview: data.preview }])
    }).catch((err) => alive && setError(getApiError(err, 'No se pudo abrir. Intenta de nuevo.')))
      .finally(() => alive && setBusy(null))
    return () => { alive = false }
  }, [initial])

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'nearest' })
  }, [bubbles, busy])

  const choose = (c: BuilderChoice) => {
    if (busy) return
    if (c.id === 'upload') {
      fileRef.current?.click()
      return
    }
    const fresh = c.id === 'new' || c.id.startsWith('resume:')
    void turn({ choice: c.id }, c.label.replace(/^🔒 /, ''), fresh ? null : step?.campaign_id ?? null)
  }

  const submit = () => {
    const text = draft.trim()
    if (!text || busy) return
    setDraft('')
    void turn({ text }, text)
  }

  const upload = async (file: File | undefined) => {
    if (!file) return
    setBusy('Subiendo tu foto…')
    setError('')
    try {
      const form = new FormData()
      form.append('file', file)
      const { data } = await api.post<{ url: string }>('/copilot/photo', form)
      setBusy(null)
      await turn({ choice: 'upload', text: data.url }, '📷 Mi foto')
    } catch (err) {
      setBusy(null)
      setError(getApiError(err, 'No se pudo subir la foto.'))
    }
  }

  const toggleMic = async () => {
    if (recording) {
      const session = recorder.current
      recorder.current = null
      setRecording(false)
      if (!session) return
      const rec = await session.stop()
      if (rec.seconds < 1) return
      setBusy('Escuchándote…')
      try {
        const form = new FormData()
        const ext = rec.mimeType.includes('mp4') ? 'mp4' : rec.mimeType.includes('ogg') ? 'ogg' : 'webm'
        form.append('audio', rec.blob, `voz.${ext}`)
        const { data } = await api.post<{ transcript: string }>('/campaigns/transcribe', form)
        setBusy(null)
        await turn({ text: data.transcript }, data.transcript)
      } catch (err) {
        setBusy(null)
        setError(getApiError(err, 'No alcancé a escucharte. Intenta de nuevo o escríbelo.'))
      }
      return
    }
    try {
      setError('')
      recorder.current = await startVoiceRecording()
      setRecording(true)
    } catch (err) {
      setError(micErrorMessage(err))
    }
  }

  const textInput = step && !step.done && step.input && step.input !== 'photo'

  return (
    <div className="flex flex-col gap-3">
      <div className="space-y-2">
        {bubbles.map((b, i) => (
          <div key={i} className={b.from === 'me' ? 'flex justify-end' : 'flex justify-start'}>
            <div className={`max-w-[85%] space-y-2 rounded-2xl px-4 py-2.5 text-sm whitespace-pre-wrap break-words ${
              b.from === 'me' ? 'rounded-tr-sm bg-brand-500 text-white' : 'rounded-tl-sm bg-muted text-foreground'
            }`}>
              {b.preview && <PreviewCard preview={b.preview} />}
              <p>{b.text}</p>
            </div>
          </div>
        ))}
        {busy && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> {busy}
          </div>
        )}
        <div ref={endRef} />
      </div>

      {error && <p role="alert" className="rounded-xl bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/30 dark:text-red-300">{error}</p>}

      {step && !step.done && step.choices.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {step.choices.map((c) => (
            <button
              key={c.id}
              onClick={() => choose(c)}
              disabled={!!busy}
              className={`rounded-full border px-3 py-1.5 text-sm font-medium transition-colors disabled:opacity-50 ${
                c.locked
                  ? 'border-border text-muted-foreground'
                  : c.id === 'web' || c.id === 'ok'
                    ? 'border-emerald-600 bg-emerald-600 text-white hover:bg-emerald-700'
                    : 'border-brand-500 text-brand-600 hover:bg-brand-50 dark:hover:bg-brand-950/30'
              }`}
            >
              {c.label}
            </button>
          ))}
        </div>
      )}

      <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp" className="hidden"
             aria-label="Subir una foto" onChange={(e) => void upload(e.target.files?.[0])} />

      {textInput && (
        <div className="flex gap-2">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit() } }}
            rows={step.input === 'edit' ? 3 : 1}
            maxLength={500}
            aria-label="Tu respuesta"
            placeholder={PLACEHOLDER[step.input ?? 'what']}
            className="flex-1 resize-none rounded-xl border border-border bg-background px-3 py-2 text-base text-foreground focus:outline-none focus:ring-2 focus:ring-brand-500"
          />
          {step.input === 'what' && canRecordVoice() && (
            <button onClick={() => void toggleMic()} disabled={!!busy && !recording}
                    aria-label={recording ? 'Terminar de grabar' : 'Decirlo con voz'}
                    className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-white disabled:opacity-60 ${recording ? 'bg-red-500 animate-pulse' : 'bg-brand-500 hover:bg-brand-600'}`}>
              {recording ? <Square className="h-5 w-5" /> : <Mic className="h-5 w-5" />}
            </button>
          )}
          <button onClick={submit} disabled={!draft.trim() || !!busy} aria-label="Enviar"
                  className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-brand-500 text-white hover:bg-brand-600 disabled:opacity-50">
            <Send className="h-5 w-5" />
          </button>
        </div>
      )}
    </div>
  )
}

function PreviewCard({ preview }: { preview: BuilderPreview }) {
  if (preview.kind === 'audio') {
    return (
      <div className="space-y-1">
        {preview.audio_url && <audio controls src={preview.audio_url} className="w-full max-w-xs" aria-label="Tu cuña" />}
        {preview.text && <details className="text-xs opacity-80"><summary className="cursor-pointer">Ver el guion</summary>{preview.text}</details>}
      </div>
    )
  }
  return (
    <div className="space-y-2 rounded-xl bg-emerald-50 p-2 text-foreground dark:bg-emerald-950/30">
      {preview.kind === 'image' && preview.image_url && (
        <img src={preview.image_url} alt="Así se ve tu promo" className="w-full max-w-xs rounded-lg" />
      )}
      {preview.text && <p>{preview.text}</p>}
    </div>
  )
}
