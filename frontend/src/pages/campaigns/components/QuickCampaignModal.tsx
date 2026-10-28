import { useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { AxiosError } from 'axios'
import { Link } from 'react-router-dom'
import { X, Mic, Square, Loader2, Sparkles, RefreshCw, Globe, MessageCircle, Search, Check } from 'lucide-react'
import api, { getApiError } from '@/lib/api'
import { useToast } from '@/contexts/ToastContext'
import { canRecordVoice, micErrorMessage, startVoiceRecording, type VoiceSession } from '@/lib/voiceRecorder'
import {
  Audience,
  Discount,
  QuickReach,
  audienceEmptyReason,
  audienceSegment,
  buildCampaignBody,
  pesos,
  previewText,
  webReachLine,
} from '../quickCampaign'

// Campaña en 3 toques: qué anuncias → la IA arma el mensaje → a quién y mandar.
// Lo avanzado (12 modos, A/B, radio, banner…) sigue en "Más opciones".

interface ContactHit {
  id: string
  name: string
  phone: string
}

interface QuickCampaignModalProps {
  businessName: string
  onClose: () => void
  onMoreOptions: () => void
}

const AUDIENCES: { value: Audience; label: string }[] = [
  { value: 'all', label: 'Todos' },
  { value: 'bought', label: 'Los que compraron' },
  { value: 'one', label: 'Uno' },
]
const DISCOUNTS: Discount[] = [10, 15, 20]

export function QuickCampaignModal({ businessName, onClose, onMoreOptions }: QuickCampaignModalProps) {
  const qc = useQueryClient()
  const { toast } = useToast()

  const [intent, setIntent] = useState('')
  const [variants, setVariants] = useState<string[]>([])
  const [variantIdx, setVariantIdx] = useState(0)
  const [message, setMessage] = useState('')
  const [generating, setGenerating] = useState(false)
  const [discount, setDiscount] = useState<Discount>(0)
  const [audience, setAudience] = useState<Audience>('all')
  const [contact, setContact] = useState<ContactHit | null>(null)
  const [search, setSearch] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  // Si "Mandar" falla después de guardar, se reintenta sobre el mismo borrador.
  const [draftId, setDraftId] = useState<string | null>(null)

  const [recording, setRecording] = useState(false)
  const [transcribing, setTranscribing] = useState(false)
  const recorder = useRef<VoiceSession | null>(null)

  const segment = audienceSegment(audience, contact?.id ?? null)
  const segmentKey = JSON.stringify(segment)
  const hasMessage = message.trim().length > 0

  const { data: reach, isFetching: reachLoading } = useQuery<QuickReach>({
    queryKey: ['campaign-reach-preview', segmentKey],
    queryFn: () => api.post('/campaigns/reach-preview', { segment }).then((r) => r.data),
    enabled: hasMessage && !(audience === 'one' && !contact),
  })

  const { data: hits } = useQuery<{ items: ContactHit[] }>({
    queryKey: ['contacts-search', search],
    queryFn: () => api.get('/contacts', { params: { q: search, status: 'active', page_size: 8 } }).then((r) => r.data),
    enabled: audience === 'one' && !contact && search.trim().length >= 2,
  })

  const generate = async (text = intent) => {
    if (!text.trim()) return
    setGenerating(true)
    setError('')
    try {
      const { data } = await api.post<{ variants: string[] }>('/campaigns/generate-content', {
        campaign_type: 'promo',
        business_name: businessName,
        intent: text.trim(),
      })
      const list = data.variants.filter((v) => v.trim())
      if (!list.length) throw new Error('vacío')
      setVariants(list)
      setVariantIdx(0)
      setMessage(list[0])
    } catch (err) {
      setError(getApiError(err, 'No pude armar el mensaje. Intenta de nuevo o escríbelo tú.'))
    } finally {
      setGenerating(false)
    }
  }

  const otherVersion = () => {
    const next = variantIdx + 1
    if (next < variants.length) {
      setVariantIdx(next)
      setMessage(variants[next])
    } else {
      void generate()
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
      setTranscribing(true)
      try {
        const form = new FormData()
        const ext = rec.mimeType.includes('mp4') ? 'mp4' : rec.mimeType.includes('ogg') ? 'ogg' : 'webm'
        form.append('audio', rec.blob, `voz.${ext}`)
        const { data } = await api.post<{ transcript: string }>('/campaigns/transcribe', form)
        setIntent(data.transcript)
        await generate(data.transcript)
      } catch (err) {
        setError(getApiError(err, 'No alcancé a escucharte. Intenta de nuevo o escríbelo.'))
      } finally {
        setTranscribing(false)
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

  const send = async (webOnly: boolean) => {
    setSending(true)
    setError('')
    const body = buildCampaignBody(intent || message, message, audience, contact?.id ?? null, discount)
    let id = draftId
    try {
      if (id) {
        await api.patch(`/campaigns/${id}`, { name: body.name, message_text: body.message_text, segment: body.segment })
      } else {
        id = (await api.post<{ id: string }>('/campaigns', body)).data.id
        setDraftId(id)
      }
      await api.post(`/campaigns/${id}/resume`, { web_only: webOnly })
      qc.invalidateQueries({ queryKey: ['campaigns'] })
      qc.invalidateQueries({ queryKey: ['dashboard'] })
      toast({
        title: 'Promo enviada',
        description: webOnly ? 'Va por la web, gratis. No se usa WhatsApp.' : 'Va por la web y por WhatsApp. Puede tardar unos minutos.',
        variant: 'success',
      })
      onClose()
    } catch (err) {
      const blocked = err instanceof AxiosError && err.response?.status === 409
      const reason = getApiError(err, 'No se pudo mandar.')
      // Lo escrito no se pierde; si ya se guardó, queda como borrador en la lista.
      setError(id || blocked ? `${reason} La promo quedó guardada como borrador.` : reason)
      qc.invalidateQueries({ queryKey: ['campaigns'] })
    } finally {
      setSending(false)
    }
  }

  const emptyReason = audienceEmptyReason(audience, contact?.id ?? null, reach)
  const canSend = hasMessage && !emptyReason && !!reach && !reachLoading && !sending
  const showWhatsApp = !!reach?.whatsapp_connected && reach.whatsapp > 0
  const busyIntent = generating || transcribing

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 dark:bg-black/80 p-4" onClick={onClose}>
      <div className="w-full max-w-lg rounded-2xl bg-card p-6 shadow-2xl max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-start justify-between gap-3">
          <h2 className="text-lg font-semibold text-foreground">Nueva promo</h2>
          <button onClick={onClose} aria-label="Cerrar" className="rounded-lg p-1 text-muted-foreground hover:bg-muted">
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* 1. ¿Qué quieres anunciar? */}
        <label htmlFor="quick-intent" className="text-sm font-medium text-foreground">¿Qué quieres anunciar?</label>
        <div className="mt-1.5 flex gap-2">
          <textarea
            id="quick-intent"
            value={intent}
            onChange={(e) => setIntent(e.target.value)}
            rows={2}
            maxLength={500}
            placeholder="Ej. 2x1 en tacos este viernes"
            className="flex-1 resize-none rounded-xl border border-border bg-background px-3 py-2 text-base text-foreground focus:outline-none focus:ring-2 focus:ring-brand-500"
          />
          {canRecordVoice() && (
            <button
              onClick={() => void toggleMic()}
              disabled={busyIntent}
              aria-label={recording ? 'Terminar de grabar' : 'Decirlo con voz'}
              className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-xl text-white disabled:opacity-60 ${recording ? 'bg-red-500 animate-pulse' : 'bg-brand-500 hover:bg-brand-600'}`}
            >
              {transcribing ? <Loader2 className="h-5 w-5 animate-spin" /> : recording ? <Square className="h-5 w-5" /> : <Mic className="h-5 w-5" />}
            </button>
          )}
        </div>
        {!hasMessage && (
          <button
            onClick={() => void generate()}
            disabled={!intent.trim() || busyIntent}
            className="mt-3 flex w-full items-center justify-center gap-2 rounded-xl bg-brand-500 px-4 py-2.5 text-sm font-semibold text-white hover:bg-brand-600 disabled:opacity-50"
          >
            {generating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
            Armar mensaje
          </button>
        )}

        {/* 2. El mensaje (armado con el catálogo real) */}
        {hasMessage && (
          <div className="mt-5 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-foreground">Así le llega al cliente</span>
              <button
                onClick={otherVersion}
                disabled={generating}
                className="flex items-center gap-1 text-xs font-medium text-brand-600 hover:underline disabled:opacity-50"
              >
                {generating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />} Otra versión
              </button>
            </div>
            <div className="rounded-2xl rounded-tl-sm bg-emerald-50 px-4 py-3 text-sm text-foreground whitespace-pre-wrap break-words dark:bg-emerald-950/30">
              {previewText(message, businessName)}
              {!!discount && <span className="mt-2 block font-semibold text-emerald-700 dark:text-emerald-400">🎟️ Cupón: {discount}% de descuento</span>}
            </div>
            <details className="text-xs text-muted-foreground">
              <summary className="cursor-pointer">Cambiar el texto</summary>
              <textarea
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                rows={4}
                aria-label="Texto del mensaje"
                className="mt-2 w-full resize-none rounded-xl border border-border bg-background px-3 py-2 text-base text-foreground focus:outline-none focus:ring-2 focus:ring-brand-500"
              />
            </details>

            <div>
              <span className="text-sm font-medium text-foreground">¿Le pones descuento?</span>
              <div className="mt-1.5 flex flex-wrap gap-2">
                {/* Ya guardada (falló "Mandar"), el descuento no se puede cambiar desde aquí. */}
                <Chip active={discount === 0} disabled={!!draftId} onClick={() => setDiscount(0)}>Sin descuento</Chip>
                {DISCOUNTS.map((d) => (
                  <Chip key={d} active={discount === d} disabled={!!draftId} onClick={() => setDiscount(d)}>{d}%</Chip>
                ))}
              </div>
            </div>

            {/* 3. ¿A quién? y mandar */}
            <div>
              <span className="text-sm font-medium text-foreground">¿A quién?</span>
              <div className="mt-1.5 flex flex-wrap gap-2">
                {AUDIENCES.map((a) => (
                  <Chip key={a.value} active={audience === a.value} onClick={() => { setAudience(a.value); setContact(null); setSearch('') }}>
                    {a.label}
                  </Chip>
                ))}
              </div>
              {audience === 'one' && (
                contact ? (
                  <div className="mt-2 flex items-center justify-between rounded-xl border border-border px-3 py-2 text-sm">
                    <span className="min-w-0 truncate"><Check className="mr-1 inline h-4 w-4 text-emerald-600" />{contact.name} · {contact.phone}</span>
                    <button onClick={() => setContact(null)} className="ml-2 shrink-0 text-xs text-brand-600 hover:underline">Cambiar</button>
                  </div>
                ) : (
                  <div className="mt-2">
                    <div className="relative">
                      <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                      <input
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        placeholder="Nombre o teléfono"
                        aria-label="Buscar cliente"
                        className="w-full rounded-xl border border-border bg-background py-2 pl-9 pr-3 text-base text-foreground focus:outline-none focus:ring-2 focus:ring-brand-500"
                      />
                    </div>
                    {!!hits?.items.length && (
                      <ul className="mt-1 divide-y divide-border rounded-xl border border-border">
                        {hits.items.map((h) => (
                          <li key={h.id}>
                            <button onClick={() => setContact(h)} className="w-full px-3 py-2 text-left text-sm hover:bg-muted">
                              <span className="block truncate font-medium text-foreground">{h.name}</span>
                              <span className="text-xs text-muted-foreground">{h.phone}</span>
                            </button>
                          </li>
                        ))}
                      </ul>
                    )}
                    {search.trim().length >= 2 && hits && !hits.items.length && (
                      <p className="mt-1 text-xs text-muted-foreground">No encontré a nadie con “{search.trim()}”.</p>
                    )}
                  </div>
                )
              )}
            </div>

            {reachLoading ? (
              <div className="flex justify-center py-2"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>
            ) : emptyReason ? (
              <p className="text-sm text-muted-foreground">{emptyReason}</p>
            ) : reach && (
              <div className="space-y-1.5 text-sm">
                <p className="flex gap-2 text-foreground"><Globe className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />{webReachLine(reach)}</p>
                {reach.whatsapp_connected ? (
                  reach.whatsapp > 0 && (
                    <p className="flex gap-2 text-muted-foreground">
                      <MessageCircle className="mt-0.5 h-4 w-4 shrink-0 text-green-600" />
                      {reach.whatsapp} más por WhatsApp si quieres (Meta te cobra aprox {pesos(reach.whatsapp_cost_mxn)})
                    </p>
                  )
                ) : (
                  <p className="flex gap-2 text-xs text-muted-foreground">
                    <MessageCircle className="mt-0.5 h-4 w-4 shrink-0" />
                    <span>
                      <Link to="/app/settings" className="font-semibold text-brand-600 hover:underline">Conecta tu chip</Link> para mandar también por WhatsApp.
                    </span>
                  </p>
                )}
              </div>
            )}
          </div>
        )}

        {error && <p role="alert" className="mt-4 rounded-xl bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/30 dark:text-red-300">{error}</p>}

        {hasMessage && (
          <div className="mt-5 flex flex-col gap-2">
            <button
              onClick={() => void send(true)}
              disabled={!canSend}
              className="flex items-center justify-center gap-2 rounded-xl bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
            >
              {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Globe className="h-4 w-4" />} Mandar gratis por web
            </button>
            {showWhatsApp && (
              <button
                onClick={() => void send(false)}
                disabled={!canSend}
                className="flex items-center justify-center gap-2 rounded-xl border border-border px-4 py-2.5 text-sm font-semibold text-foreground hover:bg-muted disabled:opacity-50"
              >
                <MessageCircle className="h-4 w-4 text-green-600" /> Mandar también por WhatsApp (aprox {pesos(reach.whatsapp_cost_mxn)})
              </button>
            )}
          </div>
        )}

        <button onClick={onMoreOptions} className="mt-4 w-full text-center text-xs font-medium text-muted-foreground hover:text-foreground hover:underline">
          Más opciones (radio, banner, secuencia, programar…)
        </button>
      </div>
    </div>
  )
}

function Chip({ active, disabled, onClick, children }: { active: boolean; disabled?: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      aria-pressed={active}
      className={`rounded-full border px-3 py-1.5 text-sm font-medium transition-colors disabled:opacity-50 ${
        active ? 'border-brand-500 bg-brand-500 text-white' : 'border-border text-foreground hover:bg-muted'
      }`}
    >
      {children}
    </button>
  )
}
