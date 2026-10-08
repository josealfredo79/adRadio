import { useEffect, useRef, useState } from 'react'
import QRCode from 'qrcode'
import { Loader2, Mic, Send, Square } from 'lucide-react'
import api, { getApiError, setAccessToken } from '@/lib/api'
import BubbleTail from '@/components/BubbleTail'
import Honeypot from '@/components/Honeypot'
import CodeWait from '@/components/CodeWait'
import OnboardingCard, { type EditField } from '@/components/OnboardingCard'
import { hoursLines } from '@/lib/onboardingDraft'
import { EMPTY_DRAFT, giroLook, progressOf, type Draft } from '@/lib/onboardingDraft'
import { verifyError } from '@/lib/codeMessages'
import { canRecordVoice, startVoiceRecording, type VoiceSession } from '@/lib/voiceRecorder'
import type { ChatPalette } from '@/lib/chatLook'

// Alta de un negocio dentro del chat de IaRadio ("✨ Quiero probarlo gratis").
// El dueño le cuenta su negocio a radiecito por voz (todo de un jalón, solo
// se pregunta lo que faltó) o con botones; su página se construye en una
// tarjeta dentro de la plática; la prueba como cliente; y la publica con su
// WhatsApp y un código — sin correo ni contraseña. Backend:
// /public/onboarding (voz y prueba) y /auth/whatsapp (código y alta).

type Msg = { who: 'bot' | 'me'; text: string }
type Stage =
  | 'resume' | 'how' | 'record' | 'name' | 'giro' | 'giro-text' | 'where' | 'hours' | 'hours-text' | 'services'
  | 'ready' | 'try' | 'change' | 'change-text' | 'fix' | 'confirm' | 'phone' | 'code' | 'done'

const SAVE_KEY = 'iaradio-onboarding-draft'
const GIROS = [
  { icon: '🌮', label: 'Comida' }, { icon: '💇', label: 'Belleza' }, { icon: '🩺', label: 'Salud' },
  { icon: '🏠', label: 'Inmobiliaria' }, { icon: '🛍️', label: 'Tienda' },
]
const week = (days: string[], open: string, close: string) =>
  Object.fromEntries(['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'].map((d) => [d, days.includes(d) ? [open, close] : null])) as Draft['business_hours']
const HOURS: { label: string; value: Draft['business_hours'] }[] = [
  { label: 'Lun a Vie · 9 a 6', value: week(['mon', 'tue', 'wed', 'thu', 'fri'], '09:00', '18:00') },
  { label: 'Lun a Sáb · 9 a 8', value: week(['mon', 'tue', 'wed', 'thu', 'fri', 'sat'], '09:00', '20:00') },
  { label: 'Todos los días · 8 a 10', value: week(['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'], '08:00', '22:00') },
]
const COLORS = [
  { icon: '🟢', label: 'Verde', value: '#2f9e44' }, { icon: '🔵', label: 'Azul', value: '#1c7ed6' },
  { icon: '🟣', label: 'Morado', value: '#7048e8' }, { icon: '🔴', label: 'Rojo', value: '#e03131' },
]
const TRY_QUESTIONS = ['¿Qué tienen?', '¿A qué hora abren?', '¿Dónde están?']

function load(): { draft: Draft; color: string | null } | null {
  try {
    const raw = localStorage.getItem(SAVE_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

function save(draft: Draft, color: string | null) {
  try {
    localStorage.setItem(SAVE_KEY, JSON.stringify({ draft, color }))
  } catch { /* sin almacenamiento: el alta sigue, solo no se recuerda */ }
}

// Lo que todavía falta, en el orden en que se pregunta.
function missing(d: Draft): Stage | null {
  if (!d.business_name) return 'name'
  if (!d.business_category) return 'giro'
  if (!(d.city || d.address)) return 'where'
  if (!d.business_hours) return 'hours'
  if (!d.services.length) return 'services'
  return null
}

const ASK: Partial<Record<Stage, string>> = {
  name: '¿Cómo se llama tu negocio?',
  giro: '¿A qué te dedicas?',
  where: '¿Dónde estás? Dime tu ciudad, o la calle si quieres.',
  hours: '¿A qué hora atiendes?',
  services: 'Dime tus 3 productos o servicios más vendidos, con precio. Escríbelos o toca 🎤.',
}

const CLEAR: Record<EditField, Partial<Draft>> = {
  name: { business_name: null }, giro: { business_category: null }, where: { city: null, address: null },
  hours: { business_hours: null }, services: { services: [] },
}
// Para confirmar cada respuesta: qué partes cambiaron y cómo quedaron.
const FIELDS: EditField[] = ['name', 'giro', 'where', 'hours', 'services']
const fieldValue = (d: Draft, f: EditField) =>
  ({ name: d.business_name, giro: d.business_category, where: [d.city, d.address], hours: d.business_hours, services: d.services })[f]
const changedFields = (a: Draft, b: Draft) => FIELDS.filter((f) => JSON.stringify(fieldValue(a, f)) !== JSON.stringify(fieldValue(b, f)))
function summaryOf(d: Draft, f: EditField): string {
  switch (f) {
    case 'name': return `• Nombre: ${d.business_name ?? '—'}`
    case 'giro': return `• Giro: ${d.business_category ?? '—'}`
    case 'where': return `• Dónde: ${[d.address, d.city].filter(Boolean).join(', ') || '—'}`
    case 'hours': return `• Horario: ${hoursLines(d.business_hours).join('; ') || '—'}`
    case 'services': return '• Productos:\n' + d.services.map((x) => `   ${x.name}${x.price != null ? ` — $${x.price}` : ''}`).join('\n')
  }
}

const FIELD_LABEL: Record<EditField, string> = {
  name: 'Nombre', giro: 'A qué me dedico', where: 'Dónde estoy', hours: 'Horario', services: 'Productos y precios',
}

export default function OnboardingFlow({
  pal, brand, onBrand, onActivity, onExit,
}: {
  pal: ChatPalette
  brand: string
  onBrand: string
  onActivity: () => void
  onExit: () => void
}) {
  const saved = useRef(load())
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [typing, setTyping] = useState(false)
  const [stage, setStage] = useState<Stage | null>(null)
  const [draft, setDraft] = useState<Draft>(EMPTY_DRAFT)
  const [color, setColor] = useState<string | null>(null)
  const [flash, setFlash] = useState<string | null>(null)
  const [trial, setTrial] = useState<[string, string][]>([])
  const [cardShown, setCardShown] = useState(false)
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [recording, setRecording] = useState(false)
  // Corrigiendo una parte ("me equivoqué"): esa parte se manda vacía para que
  // la respuesta nueva la reemplace en vez de sumarse.
  const [editing, setEditing] = useState<EditField | null>(null)
  // Lo que se acaba de anotar y espera "¿Es correcto?".
  const [confirming, setConfirming] = useState<EditField[]>([])
  const recorder = useRef<VoiceSession | null>(null)
  const [phone, setPhone] = useState('')
  const [code, setCode] = useState('')
  const [triedCode, setTriedCode] = useState('')
  const [sentAt, setSentAt] = useState(0)
  const [trap, setTrap] = useState('')
  const [published, setPublished] = useState<{ slug: string; created: boolean } | null>(null)
  const [qr, setQr] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const mic = canRecordVoice()
  const look = giroLook(draft.business_category)
  const cardColor = color ?? (draft.business_category ? look.color : brand)
  const siteUrl = `${window.location.origin}/sitio/${published?.slug ?? (draft.business_name ? slugPreview(draft.business_name) : '…')}`

  useEffect(onActivity, [msgs, typing, stage, draft, trial, published, onActivity])

  const bot = async (...lines: string[]) => {
    for (const line of lines) {
      setTyping(true)
      await new Promise((r) => setTimeout(r, 550))
      setTyping(false)
      setMsgs((m) => [...m, { who: 'bot', text: line }])
    }
  }
  const me = (t: string) => setMsgs((m) => [...m, { who: 'me', text: t }])

  const update = (patch: Partial<Draft>, part: string, newColor = color) => {
    setDraft((d) => {
      const next = { ...d, ...patch }
      save(next, newColor)
      return next
    })
    setFlash(part)
    setTimeout(() => setFlash(null), 1000)
  }

  // Ya se llegó a "¡Quedó!": después, una corrección regresa a "¿Algo más?".
  const reachedReady = useRef(false)
  const askNext = async (d: Draft, prefix?: string) => {
    const next = missing(d)
    if (!next) {
      if (reachedReady.current) {
        await bot('Listo 👍 ¿Algo más?')
        setStage('ready')
        return
      }
      reachedReady.current = true
      await bot('¡Quedó! 🎉 Ya tiene tus productos, tu horario y un asistente que contesta por ti.', 'Pruébala como si fueras tu cliente 👇')
      setStage('ready')
      return
    }
    await bot(...[prefix, ASK[next]!].filter(Boolean) as string[])
    setStage(next)
  }

  // Cada respuesta se confirma: "Anoté: … ¿Es correcto?" (✅ Sí / ✏️ No, corregir).
  const confirmChange = async (prev: Draft, next: Draft) => {
    const changed = changedFields(prev, next)
    if (!changed.length) {
      await askNext(next)
      return
    }
    setConfirming(changed)
    await bot(`Anoté:\n${changed.map((f) => summaryOf(next, f)).join('\n')}`, '¿Es correcto?')
    setStage('confirm')
  }

  // Arranque: si dejó un alta a medias en este navegador, se retoma.
  const started = useRef(false)
  useEffect(() => {
    if (started.current) return
    started.current = true
    void (async () => {
      const prev = saved.current
      if (prev?.draft?.business_name) {
        setDraft(prev.draft)
        setColor(prev.color)
        setCardShown(true)
        await bot(`¿Seguimos con ${prev.draft.business_name}? Ya tengo lo que me contaste 👆`)
        setStage('resume')
        return
      }
      await bot('¡Va! Aquí abajo se va a construir tu página mientras me cuentas 👇')
      setCardShown(true)
      await bot('¿Cómo prefieres contarme?')
      setStage('how')
    })()
  }, [])

  // Voz o texto libre → el backend ordena todo en el borrador.
  const listen = async (form: FormData, shown: string, question?: string) => {
    setBusy(true)
    setError(null)
    const base: Draft = editing ? { ...draft, ...CLEAR[editing] } : draft
    form.append('draft', JSON.stringify(base))
    if (question) form.append('question', question)
    try {
      const { data } = await api.post('/public/onboarding/listen', form)
      if (shown) me(shown)
      else me(`🎤 “${String(data.transcript).slice(0, 220)}”`)
      // Lo que el servidor no trae (vacío) no borra lo que ya se contestó con botones.
      const p = data.profile as Draft
      const next: Draft = { ...base }
      for (const [k, v] of Object.entries(p)) {
        if (v !== null && v !== '' && !(Array.isArray(v) && v.length === 0)) next[k] = v
      }
      setText('')
      const key = (d: Draft) => JSON.stringify([d.business_name, d.business_category, d.city, d.address, d.business_hours, d.services])
      if (key(next) === key(base) && !editing) {
        // No dijo nada del negocio ("¿qué es la vida?"): no fingir que se acomodó algo.
        await bot(
          stage === 'record'
            ? 'No te entendí bien 🙈 Cuéntame de tu negocio: cómo se llama, qué vendes y dónde estás. O, si prefieres, contesta con botones.'
            : 'No te entendí bien 🙈 ¿Me lo dices de otra forma?',
        )
        return
      }
      setEditing(null)
      update(next, 'hero')
      await confirmChange(draft, next)
    } catch (err) {
      setError(getApiError(err, 'No te alcancé a entender. ¿Me lo repites?'))
    } finally {
      setBusy(false)
    }
  }

  const startRec = async () => {
    setError(null)
    try {
      recorder.current = await startVoiceRecording()
      setRecording(true)
    } catch {
      setError('No pude usar el micrófono. Revisa el permiso o escríbelo.')
    }
  }
  const stopRec = async () => {
    const session = recorder.current
    recorder.current = null
    setRecording(false)
    if (!session) return
    const rec = await session.stop()
    if (rec.seconds < 1) return
    const form = new FormData()
    const ext = rec.mimeType.includes('mp4') ? 'mp4' : rec.mimeType.includes('ogg') ? 'ogg' : 'webm'
    form.append('audio', rec.blob, `voz.${ext}`)
    await listen(form, '')
  }

  const sendText = async (value: string, kind: Stage) => {
    const v = value.trim()
    if (!v) return
    // Todo pasa por la IA con la pregunta que se hizo: así "Tacos El Güero" es
    // el nombre y "es de venta de celulares" es el giro (no el nombre).
    const question: Partial<Record<Stage, string>> = {
      name: ASK.name, 'giro-text': ASK.giro, where: ASK.where, 'hours-text': ASK.hours, services: ASK.services,
      'change-text': '¿Qué le cambio a tu página?',
    }
    const form = new FormData()
    form.append('text', v)
    await listen(form, v, question[kind])
  }

  const tryAsk = async (q: string) => {
    setBusy(true)
    setError(null)
    try {
      const { data } = await api.post('/public/onboarding/try', { name: draft.business_name, profile: draft, question: q })
      setTrial((t) => [...t, [q, String(data.answer)]])
      setFlash('trial')
      setTimeout(() => setFlash(null), 1000)
    } catch (err) {
      setError(getApiError(err, 'Tu asistente no pudo contestar ahorita. Intenta de nuevo.'))
    } finally {
      setBusy(false)
    }
  }

  const askCode = async () => {
    setBusy(true)
    setError(null)
    try {
      await api.post('/auth/whatsapp/code', { phone, website: trap })
      if (stage === 'phone') me(phone)
      setStage('code')
      setSentAt(Date.now())
      await bot('Te mandé un código por WhatsApp 📲 Escríbelo aquí.')
    } catch (err) {
      setError(getApiError(err, 'No se pudo mandar el código'))
    } finally {
      setBusy(false)
    }
  }

  const publish = async (value: string) => {
    setBusy(true)
    setError(null)
    try {
      const { data } = await api.post('/auth/whatsapp/signup', {
        phone, code: value, name: draft.business_name, profile: draft, color: cardColor,
      })
      setAccessToken(data.access_token)
      try { localStorage.removeItem(SAVE_KEY) } catch { /* nada */ }
      setPublished({ slug: data.slug, created: data.created })
      setStage('done')
      if (data.created) {
        await bot('¡Publicada! 🎉 Tienes 15 días gratis. Esto ya es tuyo:')
      } else {
        await bot(`Ese WhatsApp ya tenía un negocio en IaRadio (${data.business_name}). Te dejo entrar a tu panel 👇`)
      }
    } catch (err) {
      setError(verifyError(err))
      setCode('')
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    if (stage === 'code' && code.length === 6 && code !== triedCode && !busy) {
      setTriedCode(code)
      void publish(code)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [code, stage])

  useEffect(() => {
    if (!published) return
    QRCode.toDataURL(`${window.location.origin}/sitio/${published.slug}`, { width: 480, margin: 1 }).then(setQr).catch(() => setQr(null))
  }, [published])

  const chip = (label: string, onClick: () => void, icon?: string, wide = false) => (
    <button
      key={label}
      type="button"
      onClick={onClick}
      disabled={busy}
      className={`press flex min-w-0 items-center justify-center gap-1.5 break-words rounded-xl px-1.5 py-2.5 text-center text-[13.5px] font-semibold leading-tight shadow-sm disabled:opacity-50 ${wide ? 'col-span-full' : ''}`}
      style={wide ? { background: brand, color: onBrand } : { background: pal.incoming, color: pal.accent }}
    >
      {icon && <span aria-hidden className="text-lg">{icon}</span>}
      {label}
    </button>
  )

  const pick = (label: string, then: () => void | Promise<void>) => () => { me(label); void then() }

  // "Me equivoqué": vuelve a preguntar solo esa parte (desde la tarjeta o el botón).
  const canEdit = !busy && !!stage && !['phone', 'code', 'done', 'how', 'resume', 'record'].includes(stage)
  const editField = async (f: EditField) => {
    if (!canEdit) return
    me(`✏️ Corregir: ${FIELD_LABEL[f].toLowerCase()}`)
    setEditing(f)
    setText('')
    await bot(ASK[f]!)
    setStage(f)
  }

  const field = 'min-w-0 flex-1 rounded-full px-4 py-3 text-base outline-none'
  const textDock = (placeholder: string, kind: Stage, multiline = false) => (
    <form
      className="flex items-end gap-1.5"
      onSubmit={(e) => { e.preventDefault(); void sendText(text, kind) }}
    >
      {multiline ? (
        <textarea value={text} onChange={(e) => setText(e.target.value)} placeholder={placeholder} rows={2} maxLength={600}
          className={`${field} resize-none rounded-2xl`} style={{ background: pal.field, color: pal.text }} aria-label={placeholder} autoFocus />
      ) : (
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder={placeholder} maxLength={120}
          className={field} style={{ background: pal.field, color: pal.text }} aria-label={placeholder} autoFocus />
      )}
      {mic && !text.trim() && kind !== 'name' ? (
        <button type="button" onClick={() => void (recording ? stopRec() : startRec())} disabled={busy}
          aria-label={recording ? 'Terminar de hablar' : 'Decírtelo'}
          className="press flex h-12 w-12 shrink-0 items-center justify-center rounded-full shadow-sm disabled:opacity-50"
          style={{ background: recording ? '#f43f5e' : brand, color: recording ? '#fff' : onBrand }}>
          {recording ? <Square size={16} fill="currentColor" /> : <Mic size={21} />}
        </button>
      ) : (
        <button type="submit" disabled={!text.trim() || busy} aria-label="Enviar"
          className="press flex h-12 w-12 shrink-0 items-center justify-center rounded-full shadow-sm disabled:opacity-50"
          style={{ background: brand, color: onBrand }}>
          {busy ? <Loader2 size={18} className="animate-spin" /> : <Send size={19} />}
        </button>
      )}
    </form>
  )

  const dock = (() => {
    switch (stage) {
      case 'resume':
        return <div className="grid grid-cols-2 gap-2">
          {chip('Sí, seguir', pick('Sí, seguir', () => askNext(draft)), '👍')}
          {chip('Empezar de nuevo', pick('Empezar de nuevo', async () => { setDraft(EMPTY_DRAFT); setColor(null); save(EMPTY_DRAFT, null); await bot('¿Cómo prefieres contarme?'); setStage('how') }), '🔄')}
        </div>
      case 'how':
        return <div className="grid gap-2">
          {mic && chip('Te lo digo por voz', pick('Te lo digo por voz', async () => {
            await bot('Toca el micrófono y cuéntame de corrido: cómo se llama, qué vendes, dónde estás, tu horario y tus 3 productos más vendidos con precio. Yo acomodo todo 🙌')
            setStage('record')
          }), '🎤', true)}
          {chip('Contestar con botones', pick('Contestar con botones', () => askNext(draft)), '👆', true)}
        </div>
      case 'record':
        return <div className="flex flex-col items-center gap-2 py-1">
          <button type="button" onClick={() => void (recording ? stopRec() : startRec())} disabled={busy}
            aria-label={recording ? 'Terminar de hablar' : 'Hablar'}
            className="press flex h-16 w-16 items-center justify-center rounded-full text-white shadow-lg disabled:opacity-50"
            style={{ background: recording ? '#f43f5e' : brand }}>
            {busy ? <Loader2 className="animate-spin" /> : recording ? <Square size={20} fill="currentColor" /> : <Mic size={26} />}
          </button>
          <p className="text-xs" style={{ color: pal.meta }}>
            {busy ? 'Acomodando lo que me dijiste…' : recording ? '🔴 Te escucho… toca otra vez al terminar' : 'Toca para hablar'}
          </p>
          {!recording && !busy && (
            <button type="button" className="text-xs underline" style={{ color: pal.meta }} onClick={() => void askNext(draft, 'Va, mejor con botones.')}>
              Prefiero contestar con botones
            </button>
          )}
        </div>
      case 'name': return textDock('Escribe aquí el nombre de tu negocio', 'name')
      case 'giro':
        return <div className="grid grid-cols-3 gap-2">
          {GIROS.map((g) => chip(g.label, pick(g.label, async () => {
            const next = { ...draft, business_category: g.label }
            setEditing(null)
            update(next, 'hero')
            await confirmChange(draft, next)
          }), g.icon))}
          {chip('Otro', pick('Otro', async () => { await bot('¿A qué te dedicas?'); setStage('giro-text') }), '✏️')}
        </div>
      case 'giro-text': return textDock('Ej. papelería, taller mecánico…', 'giro-text')
      case 'where': return textDock('Escribe tu ciudad, o calle y ciudad', 'where')
      case 'hours':
        return <div className="grid grid-cols-2 gap-2">
          {HOURS.map((h) => chip(h.label, pick(h.label, async () => {
            const next = { ...draft, business_hours: h.value }
            setEditing(null)
            update(next, 'hours')
            await confirmChange(draft, next)
          })))}
          {chip('Otro horario', pick('Otro horario', async () => { await bot('Dime tu horario, por ejemplo: martes a domingo de 2 a 11.'); setStage('hours-text') }), '✏️')}
        </div>
      case 'hours-text': return textDock('Ej. Mar a Dom de 2 a 11', 'hours-text')
      case 'services': return textDock('Ej. Orden de pastor 85, quesadilla 45…', 'services', true)
      case 'ready':
        return <div className="grid grid-cols-2 gap-2">
          {chip('Probar como cliente', pick('Probar como cliente', async () => {
            await bot('Toca una pregunta como si fueras tu cliente. En la tarjeta 👆 vas a ver lo que le contestaría tu asistente.')
            setStage('try')
          }), '🧪')}
          {chip('Cambiar algo', pick('Cambiar algo', async () => { await bot('¿Qué le cambio? También me lo puedes decir con tu voz.'); setStage('change') }), '🎨')}
          {chip('Publicar mi página', pick('Publicar mi página', async () => {
            await bot('Para que no se pierda y te avise cuando un cliente te escriba, ¿cuál es tu WhatsApp?', 'Te mando un código. Nada de contraseñas.')
            setStage('phone')
          }), '🚀', true)}
        </div>
      case 'try':
        return <div className="grid grid-cols-3 gap-2">
          {TRY_QUESTIONS.map((q) => chip(q, () => void tryAsk(q)))}
          {chip('Listo, ya vi', pick('Listo, ya vi', async () => { await bot('Así le va a contestar a tus clientes, de día y de noche. ¿Publicamos?'); setStage('ready') }), '✅', true)}
        </div>
      case 'change':
        return <div className="grid grid-cols-4 gap-2">
          {COLORS.map((c) => chip(c.label, pick(c.label, async () => {
            setColor(c.value)
            update({}, 'hero', c.value)
            await bot('¿Qué tal así? 👆')
            setStage('ready')
          }), c.icon))}
          {chip('Otra cosa (precio, horario…)', pick('Otra cosa', async () => { await bot('Dime qué le cambio, por ejemplo: "la quesadilla a 50".'); setStage('change-text') }), '✏️', true)}
          {chip('Así está perfecto', pick('Así está perfecto', async () => { await bot('¡Va! ¿Publicamos?'); setStage('ready') }), '✅', true)}
        </div>
      case 'change-text': return textDock('Ej. la quesadilla a 50', 'change-text')
      case 'confirm':
        return <div className="grid grid-cols-2 gap-2">
          {chip('Sí, es correcto', pick('✅ Sí', async () => {
            setConfirming([])
            if (!missing(draft) && reachedReady.current) {
              await bot('Listo 👍 ¿Algo más?')
              setStage('ready')
              return
            }
            await askNext(draft)
          }), '✅')}
          {chip('No, corregir', () => {
            const f = confirming
            setConfirming([])
            if (f.length === 1) void editField(f[0])
            else { me('✏️ No, corregir'); void bot('¿Qué corrijo?').then(() => setStage('fix')) }
          }, '✏️')}
        </div>
      case 'fix':
        return <div className="grid grid-cols-2 gap-2">
          {(Object.keys(FIELD_LABEL) as EditField[]).map((f) => chip(FIELD_LABEL[f], () => void editField(f)))}
          {chip('Nada, seguir', pick('Nada, seguir', () => askNext(draft)), '👍', true)}
        </div>
      case 'phone':
        return <form className="flex items-end gap-1.5" onSubmit={(e) => { e.preventDefault(); void askCode() }}>
          <Honeypot value={trap} onChange={setTrap} />
          <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="Tu WhatsApp (10 dígitos)" type="tel"
            inputMode="tel" autoComplete="tel" maxLength={20} className={field} style={{ background: pal.field, color: pal.text }} aria-label="Tu WhatsApp" autoFocus />
          <button type="submit" disabled={phone.replace(/\D/g, '').length < 10 || busy} aria-label="Mandarme el código"
            className="press flex h-12 w-12 shrink-0 items-center justify-center rounded-full shadow-sm disabled:opacity-50"
            style={{ background: brand, color: onBrand }}>
            {busy ? <Loader2 size={18} className="animate-spin" /> : <Send size={19} />}
          </button>
        </form>
      case 'code':
        return <div className="grid gap-2">
          <input value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))} placeholder="123456"
            inputMode="numeric" autoComplete="one-time-code" maxLength={6} autoFocus aria-label="Código"
            className="w-full rounded-full px-4 py-3 text-center text-xl tracking-[0.4em] outline-none" style={{ background: pal.field, color: pal.text }} />
          <CodeWait sentAt={sentAt} muted={pal.meta} accent={brand} onResend={() => { setCode(''); void askCode() }} />
          <button type="button" className="text-left text-xs underline" style={{ color: pal.meta }} onClick={() => { setStage('phone'); setCode(''); setError(null) }}>
            Cambiar número
          </button>
        </div>
      case 'done':
        return <div className="grid gap-2">
          <a href="/app" className="press flex items-center justify-center gap-2 rounded-xl py-3 text-[15px] font-semibold shadow-sm" style={{ background: brand, color: onBrand }}>
            📊 Entrar a mi panel
          </a>
          <button type="button" onClick={onExit} className="text-xs underline" style={{ color: pal.meta }}>Volver al chat</button>
        </div>
      default:
        return null
    }
  })()

  const shareText = `Ya puedes pedir y agendar en línea en ${draft.business_name} ✨ ${siteUrl}`

  return (
    <>
      {msgs.map((m, i) => {
        const mine = m.who === 'me'
        const first = i === 0 || msgs[i - 1].who !== m.who
        return (
          <div key={i} className={`anim-bubble flex ${mine ? 'justify-end' : 'justify-start'} ${first ? 'mt-2.5' : 'mt-1'}`}>
            <div className="relative max-w-[82%] whitespace-pre-line rounded-lg px-2.5 py-1.5 text-[15px] leading-snug shadow-sm"
              style={{ background: mine ? pal.outgoing : pal.incoming, color: pal.text, ...(first ? (mine ? { borderTopRightRadius: 0 } : { borderTopLeftRadius: 0 }) : {}) }}>
              {first && <BubbleTail side={mine ? 'right' : 'left'} fill={mine ? pal.outgoing : pal.incoming} />}
              {m.text}
            </div>
          </div>
        )
      })}

      {/* La tarjeta siempre va al final: es lo que se está construyendo ahora. */}
      {cardShown && (
        <div className="flex justify-start">
          <OnboardingCard draft={draft} color={cardColor} pal={pal} flash={flash} trial={trial}
            published={!!published} link={siteUrl.replace(/^https?:\/\//, '')}
            onEdit={canEdit ? (f) => void editField(f) : undefined} />
        </div>
      )}

      {published && (
        <div className="anim-bubble mt-2 grid max-w-[min(94%,26rem)] gap-2">
          <div className="grid gap-2 rounded-xl p-3 shadow-sm" style={{ background: pal.incoming, color: pal.text }}>
            <p className="text-sm font-semibold">Tu link</p>
            <div className="flex flex-wrap items-center gap-2">
              <code className="min-w-0 flex-1 break-all text-xs">{siteUrl}</code>
              <button type="button" className="press rounded-full px-3 py-1.5 text-xs font-semibold" style={{ background: pal.bar, color: pal.text, border: `1px solid ${pal.meta}55` }}
                onClick={() => { navigator.clipboard?.writeText(siteUrl).then(() => setCopied(true)).catch(() => setCopied(false)) }}>
                {copied ? 'Copiado ✓' : 'Copiar'}
              </button>
              <a href={siteUrl} target="_blank" rel="noreferrer" className="rounded-full px-3 py-1.5 text-xs font-semibold" style={{ background: pal.bar, color: pal.text, border: `1px solid ${pal.meta}55` }}>Ver</a>
            </div>
          </div>
          {qr && (
            <div className="flex items-center gap-3 rounded-xl p-3 shadow-sm" style={{ background: pal.incoming, color: pal.text }}>
              <img src={qr} alt={`QR de ${draft.business_name}`} className="h-20 w-20 shrink-0 rounded bg-white p-1" />
              <div className="grid gap-1.5">
                <p className="text-sm font-semibold">QR para tu mostrador</p>
                <p className="text-xs" style={{ color: pal.meta }}>Imprímelo y pégalo donde te paguen.</p>
                <a href={qr} download={`qr-${published.slug}.png`} className="w-fit rounded-full px-3 py-1.5 text-xs font-semibold" style={{ background: pal.bar, color: pal.text, border: `1px solid ${pal.meta}55` }}>Descargar</a>
              </div>
            </div>
          )}
          <div className="grid gap-2 rounded-xl p-3 shadow-sm" style={{ background: pal.incoming, color: pal.text }}>
            <p className="text-sm font-semibold">Para tu Estado de WhatsApp</p>
            <div className="rounded-lg p-3 font-extrabold leading-tight text-white" style={{ background: `linear-gradient(150deg, ${cardColor}, #1a1238)` }}>
              Ya puedes pedir y agendar en línea en {draft.business_name} ✨
              <span className="mt-1 block text-xs font-medium opacity-90">{siteUrl.replace(/^https?:\/\//, '')}</span>
            </div>
            <a href={`https://wa.me/?text=${encodeURIComponent(shareText)}`} target="_blank" rel="noreferrer"
              className="press w-fit rounded-full px-4 py-2 text-sm font-semibold" style={{ background: '#25d366', color: '#0b2914' }}>
              Compartir en WhatsApp
            </a>
          </div>
        </div>
      )}

      {typing && (
        <div className="mt-2.5 flex justify-start">
          <div className="relative flex items-center gap-1 rounded-lg px-3.5 py-3 shadow-sm" style={{ background: pal.incoming, borderTopLeftRadius: 0 }} aria-label="Escribiendo…">
            <BubbleTail side="left" fill={pal.incoming} />
            {[0, 1, 2].map((d) => <span key={d} className="typing-dot h-2 w-2 rounded-full" style={{ background: pal.meta, animationDelay: `${d * 160}ms` }} />)}
          </div>
        </div>
      )}

      {stage && !typing && (
        <div className="sticky bottom-0 -mx-3 mt-3 grid gap-2 px-3 pb-1 pt-2" style={{ background: `linear-gradient(to bottom, transparent, ${pal.wallpaper} 18%)` }}>
          {error && <p className="rounded-lg px-3 py-1.5 text-xs text-rose-600 shadow-sm" style={{ background: pal.incoming }}>{error}</p>}
          {dock}
          {stage !== 'done' && stage !== 'phone' && stage !== 'code' && (
            <div className="flex items-center justify-center gap-4 text-[12px]" style={{ color: pal.meta }}>
              {canEdit && stage !== 'fix' && progressOf(draft) > 0 && (
                <button type="button" className="underline" onClick={() => {
                  me('✏️ Me equivoqué')
                  void bot('Sin problema. ¿Qué corrijo? También puedes tocar esa parte en la tarjeta 👆').then(() => setStage('fix'))
                }}>✏️ Me equivoqué</button>
              )}
              <button type="button" onClick={onExit} className="underline">Salir del alta</button>
            </div>
          )}
        </div>
      )}
    </>
  )
}

function slugPreview(name: string): string {
  return name.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 44) || 'mi-negocio'
}
