import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api'
import { Megaphone, Plus, Play, Pause, Trash2, Sparkles, Radio, ListOrdered, Ticket, CalendarClock, BarChart2, X, CalendarRange, CheckCircle2, AlertCircle } from 'lucide-react'

interface Campaign {
  id: string
  name: string
  type: string
  message_text: string
  status: string
  stats: Record<string, number>
  ab_test: Record<string, any>
  created_at: string
  schedule?: { start_date?: string; end_date?: string } | null
}

const CAMPAIGN_TYPES = [
  { value: 'promo', label: '🎁 Promoción' },
  { value: 'reminder', label: '⏰ Recordatorio' },
  { value: 'launch', label: '🚀 Lanzamiento' },
  { value: 'event', label: '🎉 Evento' },
]

// Modos de campaña — La Nueva Radio
const CAMPAIGN_MODES = [
  { value: 'regular', label: '📢 Regular', desc: 'Un mensaje personalizado con nombre y ciudad' },
  { value: 'sequence', label: '📻 Secuencia', desc: '3 mensajes en días 1, 3 y 5 — como un programa de radio' },
  { value: 'saga', label: '🎭 Saga', desc: '4 episodios semanales — radionovela de tu negocio' },
  { value: 'radio', label: '🎙️ Cuña clásica', desc: 'Audio estilo radio AM/FM de los 80s con voz de locutor' },
  { value: 'comunitaria', label: '🌿 Radio Comunitaria', desc: 'Primero un consejo genuino, luego tu negocio' },
  { value: 'capsula', label: '💡 Cápsula del Día', desc: 'Dato sorprendente + mención natural del negocio' },
  { value: 'trivia', label: '🧠 Trivia del Día', desc: 'Pregunta curiosa + respuesta + negocio — perfecto para interacción' },
  { value: 'historia', label: '📖 Mini Historia', desc: 'Radionovela de 30s: personaje → problema → tu negocio como solución' },
  { value: 'alerta', label: '🚨 Alerta de Servicio', desc: 'Info contextual oportuna (clima, fecha) + tu negocio' },
  { value: 'estacional', label: '🗓️ Cuña Estacional', desc: 'Conecta tu negocio con el momento exacto del año' },
]

const STATUS_COLORS: Record<string, string> = {
  draft: 'bg-gray-100 text-gray-600',
  scheduled: 'bg-blue-100 text-blue-600',
  running: 'bg-green-100 text-green-600',
  paused: 'bg-yellow-100 text-yellow-600',
  completed: 'bg-purple-100 text-purple-600',
}

const STATUS_LABELS: Record<string, string> = {
  draft: 'Borrador', scheduled: 'Programada',
  running: 'Activa', paused: 'Pausada', completed: 'Completada',
}

const MODE_BADGE: Record<string, string> = {
  sequence: '📻 Secuencia',
  saga: '🎭 Saga',
  radio: '🎙️ Cuña de radio',
  comunitaria: '🌿 Radio Comunitaria',
  capsula: '💡 Cápsula',
  trivia: '🧠 Trivia',
  historia: '📖 Historia',
  alerta: '🚨 Alerta',
  estacional: '🗓️ Estacional',
}

type CampaignMode = 'regular' | 'sequence' | 'saga' | 'radio' | 'comunitaria' | 'capsula' | 'trivia' | 'historia' | 'alerta' | 'estacional'

const AUDIO_MODES: CampaignMode[] = ['radio', 'comunitaria', 'capsula', 'trivia', 'historia', 'alerta', 'estacional']

export default function CampaignsPage() {
  const qc = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState({ name: '', type: 'promo', message_text: '' })
  const [mode, setMode] = useState<CampaignMode>('regular')
  const [generating, setGenerating] = useState(false)
  const [variants, setVariants] = useState<string[]>([])
  const [multiMessages, setMultiMessages] = useState<string[]>([])

  const { data: dashData } = useQuery<{ messages_remaining: number }>({
    queryKey: ['dashboard'],
    queryFn: () => api.get('/dashboard').then((r) => r.data),
    staleTime: 1000 * 60 * 5,
  })
  const noCredits = (dashData?.messages_remaining ?? 1) <= 0
  const [intent, setIntent] = useState('')
  const [productDesc, setProductDesc] = useState('')
  const [protagonist, setProtagonist] = useState('María')
  const [hasCoupon, setHasCoupon] = useState(false)
  const [couponDesc, setCouponDesc] = useState('')
  const [couponHours, setCouponHours] = useState(72)
  const [radioCountry, setRadioCountry] = useState('mx')
  const [radioAudioUrl, setRadioAudioUrl] = useState('')
  const [radioScript, setRadioScript] = useState('')
  const [extraContext, setExtraContext] = useState('')
  const [businessCategory, setBusinessCategory] = useState('')
  const [scheduledAt, setScheduledAt] = useState('')
  const [error, setError] = useState('')
  const [analyticsId, setAnalyticsId] = useState<string | null>(null)

  // Parrilla Semanal
  const [showParrilla, setShowParrilla] = useState(false)
  const [parrillaBusinessName, setParrillaBusinessName] = useState('')
  const [parrillaIntent, setParrillaIntent] = useState('')
  const [parrillaCategory, setParrillaCategory] = useState('')
  const [parrillaContext, setParrillaContext] = useState('')
  const [parrillaCountry, setParrillaCountry] = useState('mx')
  const [parrillaSendTime, setParrillaSendTime] = useState('10:00')
  const [parrillaAutoSchedule, setParrillaAutoSchedule] = useState(false)
  const [parrillaGenerating, setParrillaGenerating] = useState(false)
  const [parrillaResult, setParrillaResult] = useState<{
    days: { day: number; day_name: string; mode: string; mode_emoji: string; script: string; audio_url: string | null }[]
    plan: string
    auto_scheduled: boolean
  } | null>(null)
  const [parrillaError, setParrillaError] = useState('')

  const { data: campaigns, isLoading } = useQuery<Campaign[]>({
    queryKey: ['campaigns'],
    queryFn: () => api.get('/campaigns').then((r) => r.data),
  })

  const createMutation = useMutation({
    mutationFn: (body: any) => api.post('/campaigns', body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['campaigns'] }); setShowCreate(false); resetForm() },
    onError: (err: any) => setError(err.response?.data?.detail ?? 'Error'),
  })

  const pauseMutation = useMutation({
    mutationFn: (id: string) => api.post(`/campaigns/${id}/pause`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['campaigns'] }),
  })
  const resumeMutation = useMutation({
    mutationFn: (id: string) => api.post(`/campaigns/${id}/resume`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['campaigns'] }),
  })
  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/campaigns/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['campaigns'] }),
  })

  const resetForm = () => {
    setForm({ name: '', type: 'promo', message_text: '' })
    setMode('regular'); setVariants([]); setMultiMessages([])
    setIntent(''); setProductDesc(''); setProtagonist('María')
    setHasCoupon(false); setCouponDesc(''); setCouponHours(72)
    setRadioCountry('mx'); setRadioAudioUrl(''); setRadioScript('')
    setExtraContext(''); setBusinessCategory('')
    setScheduledAt(''); setError('')
  }

  const generateContent = async () => {
    if (!form.name) return
    setGenerating(true)
    setError('')
    try {
      if (mode === 'regular') {
        const { data } = await api.post('/campaigns/generate-content', {
          campaign_type: form.type, business_name: form.name, intent,
        })
        setVariants(data.variants)
      } else if (mode === 'sequence') {
        const { data } = await api.post('/campaigns/generate-sequence', {
          business_name: form.name, intent, campaign_type: form.type,
        })
        setMultiMessages(data.messages)
      } else if (mode === 'saga') {
        const { data } = await api.post('/campaigns/generate-saga', {
          business_name: form.name, product_description: productDesc, protagonist_name: protagonist,
        })
        setMultiMessages(data.messages)
      } else if (AUDIO_MODES.includes(mode)) {
        const { data } = await api.post('/campaigns/generate-radio-ad', {
          business_name: form.name, intent, country: radioCountry,
          mode: mode === 'radio' ? 'classic' : mode,
          business_category: businessCategory || undefined,
          extra_context: extraContext || undefined,
        })
        setRadioAudioUrl(data.audio_url)
        setRadioScript(data.script ?? '')
      }
    } catch (err: any) {
      setError(err.response?.data?.detail ?? 'Error al generar contenido')
    } finally {
      setGenerating(false)
    }
  }

  const generateParrilla = async () => {
    if (!parrillaBusinessName || !parrillaIntent) return
    setParrillaGenerating(true)
    setParrillaError('')
    try {
      const { data } = await api.post('/campaigns/generate-parrilla', {
        business_name: parrillaBusinessName,
        intent: parrillaIntent,
        country: parrillaCountry,
        business_category: parrillaCategory || undefined,
        extra_context: parrillaContext || undefined,
        auto_schedule: parrillaAutoSchedule,
        send_time: parrillaSendTime,
      })
      setParrillaResult(data)
    } catch (err: any) {
      setParrillaError(err.response?.data?.detail ?? 'Error al generar parrilla')
    } finally {
      setParrillaGenerating(false)
    }
  }

  const handleCreate = () => {
    const ab_test: Record<string, any> = {
      campaign_mode: mode,
      has_coupon: hasCoupon,
      coupon_description: couponDesc,
      coupon_hours: couponHours,
    }
    if (mode !== 'regular' && multiMessages.length > 0) {
      ab_test.messages = multiMessages
    }
    if (AUDIO_MODES.includes(mode)) {
      ab_test.audio_url = radioAudioUrl
      ab_test.radio_script = radioScript
    }
    const schedule = scheduledAt ? { start_date: new Date(scheduledAt).toISOString() } : {}
    const campaignStatus = scheduledAt ? 'scheduled' : 'draft'
    createMutation.mutate({
      ...form,
      message_text: form.message_text || radioScript,
      ab_test,
      schedule,
      status: campaignStatus,
    })
  }

  const analyticsTarget = campaigns?.find((c) => c.id === analyticsId)

  const isMultiMode = mode === 'sequence' || mode === 'saga'
  const isRadioMode = AUDIO_MODES.includes(mode)
  const readyToCreate = form.name && (
    (mode === 'regular' && form.message_text) ||
    (isMultiMode && multiMessages.length > 0) ||
    (isRadioMode && !!radioAudioUrl)
  )

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Campañas</h1>
          <p className="mt-1 text-sm text-gray-500">{campaigns?.length ?? 0} campañas creadas</p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={() => setShowParrilla(true)}
            className="flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
          >
            <CalendarRange className="h-4 w-4 text-brand-500" /> Parrilla Semanal
          </button>
          <button
            onClick={() => setShowCreate(true)}
            disabled={noCredits}
            title={noCredits ? 'Sin mensajes disponibles — adquiere un plan para continuar' : undefined}
            className="flex items-center gap-2 rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Plus className="h-4 w-4" /> Nueva campaña
          </button>
        </div>
      </div>

      {/* No credits warning */}
      {noCredits && (
        <div className="rounded-xl border border-orange-200 bg-orange-50 px-5 py-4 flex items-center justify-between">
          <div>
            <p className="text-sm font-semibold text-orange-800">Sin mensajes disponibles</p>
            <p className="text-xs text-orange-600">Adquiere un plan para crear y enviar campañas.</p>
          </div>
          <a
            href="/plans"
            className="shrink-0 rounded-lg bg-orange-500 px-4 py-2 text-xs font-medium text-white hover:bg-orange-600 transition-colors"
          >
            Ver planes →
          </a>
        </div>
      )}

      {/* Campaigns list */}
      <div className="space-y-3">
        {isLoading ? (
          Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-24 rounded-xl bg-gray-100 animate-pulse" />
          ))
        ) : campaigns?.length === 0 ? (
          <div className="flex flex-col items-center justify-center rounded-xl bg-white py-16 shadow-sm border border-gray-100 text-gray-400">
            <Radio className="h-12 w-12 mb-3" />
            <p className="text-sm font-medium">No hay campañas todavía</p>
            <p className="text-xs mt-1">Crea tu primera campaña — regular, secuencia o saga</p>
          </div>
        ) : (
          campaigns?.map((campaign) => (
            <div key={campaign.id} className="rounded-xl bg-white p-5 shadow-sm border border-gray-100">
              <div className="flex items-start justify-between">
                <div className="flex-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="font-semibold text-gray-900 truncate">{campaign.name}</h3>
                    <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_COLORS[campaign.status] ?? 'bg-gray-100 text-gray-600'}`}>
                      {STATUS_LABELS[campaign.status] ?? campaign.status}
                    </span>
                    {campaign.ab_test?.campaign_mode && campaign.ab_test.campaign_mode !== 'regular' && (
                      <span className="rounded-full bg-purple-100 px-2.5 py-0.5 text-xs font-medium text-purple-600">
                        {MODE_BADGE[campaign.ab_test.campaign_mode]}
                      </span>
                    )}
                    {campaign.ab_test?.has_coupon && (
                      <span className="rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-medium text-amber-600">
                        🎫 Con cupón
                      </span>
                    )}
                  </div>
                  <p className="mt-1.5 text-sm text-gray-500 line-clamp-2">{campaign.message_text}</p>
                  {campaign.ab_test?.audio_url && (
                    <div className="mt-3">
                      <audio controls src={campaign.ab_test.audio_url} className="h-8 w-full max-w-md rounded-lg" />
                    </div>
                  )}
                  <div className="mt-3 flex flex-wrap gap-3 text-xs text-gray-400">
                    <span>📤 {campaign.stats.sent ?? 0} enviados</span>
                    <span>✅ {campaign.stats.delivered ?? 0} entregados</span>
                    <span>💬 {campaign.stats.replied ?? 0} respondidos</span>
                    <span>🎫 {campaign.stats.coupons_redeemed ?? 0} canjeados</span>
                  </div>
                  {(campaign.stats.sent ?? 0) > 0 && (
                    <div className="mt-3 flex flex-wrap items-center gap-4">
                      {/* Delivery rate */}
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] text-gray-400 whitespace-nowrap">Entrega</span>
                        <div className="h-1.5 w-20 overflow-hidden rounded-full bg-gray-100">
                          <div
                            className="h-full rounded-full bg-green-400 transition-all"
                            style={{ width: `${Math.min(100, Math.round(((campaign.stats.delivered ?? 0) / campaign.stats.sent) * 100))}%` }}
                          />
                        </div>
                        <span className="text-[10px] font-semibold text-green-600">
                          {Math.round(((campaign.stats.delivered ?? 0) / campaign.stats.sent) * 100)}%
                        </span>
                      </div>
                      {/* Response rate */}
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] text-gray-400 whitespace-nowrap">Respuesta</span>
                        <div className="h-1.5 w-20 overflow-hidden rounded-full bg-gray-100">
                          <div
                            className="h-full rounded-full bg-brand-500 transition-all"
                            style={{ width: `${Math.min(100, Math.round(((campaign.stats.replied ?? 0) / campaign.stats.sent) * 100))}%` }}
                          />
                        </div>
                        <span className="text-[10px] font-semibold text-brand-600">
                          {Math.round(((campaign.stats.replied ?? 0) / campaign.stats.sent) * 100)}%
                        </span>
                      </div>
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-2 ml-4">
                  <button onClick={() => setAnalyticsId(campaign.id)}
                    className="rounded-lg border border-gray-200 p-1.5 text-gray-500 hover:bg-gray-50 transition-colors">
                    <BarChart2 className="h-3.5 w-3.5" />
                  </button>
                  {campaign.status === 'running' && (
                    <button onClick={() => pauseMutation.mutate(campaign.id)}
                      className="rounded-lg border border-yellow-200 bg-yellow-50 p-1.5 text-yellow-600 hover:bg-yellow-100">
                      <Pause className="h-3.5 w-3.5" />
                    </button>
                  )}
                  {(campaign.status === 'paused' || campaign.status === 'draft' || campaign.status === 'scheduled') && (
                    <button onClick={() => resumeMutation.mutate(campaign.id)}
                      title={campaign.status === 'draft' ? "Enviar campaña ahora" : campaign.status === 'scheduled' ? "Forzar envío ahora" : "Reanudar campaña"}
                      className="rounded-lg border border-green-200 bg-green-50 p-1.5 text-green-600 hover:bg-green-100 transition-colors">
                      <Play className="h-3.5 w-3.5" />
                    </button>
                  )}
                  <button onClick={() => { if (confirm('¿Eliminar esta campaña?')) deleteMutation.mutate(campaign.id) }}
                    className="text-gray-400 hover:text-red-500 transition-colors">
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Create Modal */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-2xl rounded-2xl bg-white p-6 shadow-2xl max-h-[92vh] overflow-y-auto">
            <h3 className="mb-5 text-lg font-semibold text-gray-900">Nueva campaña</h3>

            <div className="space-y-4">
              {/* Nombre + tipo */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-gray-700">Nombre</label>
                  <input type="text" placeholder="Ej: Promo verano"
                    value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
                    className="w-full rounded-lg border border-gray-300 px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none" />
                </div>
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-gray-700">Tipo</label>
                  <select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}
                    className="w-full rounded-lg border border-gray-300 px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none">
                    {CAMPAIGN_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
                  </select>
                </div>
              </div>

              {/* Modo de campaña — La Nueva Radio */}
              <div>
                <label className="mb-2 block text-sm font-medium text-gray-700">🎙️ Modo de campaña</label>
                <div className="grid grid-cols-2 gap-2">
                  {CAMPAIGN_MODES.map((m) => (
                    <button key={m.value} onClick={() => { setMode(m.value as CampaignMode); setVariants([]); setMultiMessages([]); setRadioAudioUrl(''); setRadioScript('') }}
                      className={`rounded-xl border p-3 text-left transition-all ${mode === m.value ? 'border-brand-500 bg-brand-50' : 'border-gray-200 hover:border-gray-300'}`}>
                      <div className="text-sm font-medium text-gray-900">{m.label}</div>
                      <div className="mt-0.5 text-xs text-gray-500">{m.desc}</div>
                    </button>
                  ))}
                </div>
              </div>

              {/* Inputs según modo */}
              {mode === 'regular' && (
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-gray-700">¿Qué quieres comunicar?</label>
                  <textarea rows={2} placeholder="Ej: 30% de descuento este fin de semana"
                    value={intent} onChange={(e) => setIntent(e.target.value)}
                    className="w-full rounded-lg border border-gray-300 px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none resize-none" />
                  <p className="mt-1 text-xs text-gray-400">
                    Puedes usar <code>{'{{nombre}}'}</code>, <code>{'{{ciudad}}'}</code> en el mensaje para personalización automática
                  </p>
                </div>
              )}
              {mode === 'sequence' && (
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-gray-700">¿Qué historia cuenta la secuencia?</label>
                  <textarea rows={2} placeholder="Ej: Lanzamiento de nuevos platillos de temporada"
                    value={intent} onChange={(e) => setIntent(e.target.value)}
                    className="w-full rounded-lg border border-gray-300 px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none resize-none" />
                  <p className="mt-1 text-xs text-gray-400">Claude creará 3 mensajes para días 1, 3 y 5</p>
                </div>
              )}
              {mode === 'saga' && (
                <div className="space-y-3">
                  <div>
                    <label className="mb-1.5 block text-sm font-medium text-gray-700">¿Qué producto/servicio protagoniza la saga?</label>
                    <textarea rows={2} placeholder="Ej: Clases de yoga para mamás con poco tiempo"
                      value={productDesc} onChange={(e) => setProductDesc(e.target.value)}
                      className="w-full rounded-lg border border-gray-300 px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none resize-none" />
                  </div>
                  <div>
                    <label className="mb-1.5 block text-sm font-medium text-gray-700">Nombre del protagonista</label>
                    <input type="text" value={protagonist} onChange={(e) => setProtagonist(e.target.value)}
                      className="w-full rounded-lg border border-gray-300 px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none" />
                  </div>
                  <p className="text-xs text-gray-400">Claude creará 4 episodios semanales al estilo radionovela 📻</p>
                </div>
              )}
              {isRadioMode && (
                <div className="space-y-3">
                  <div>
                    <label className="mb-1.5 block text-sm font-medium text-gray-700">
                      {mode === 'comunitaria' ? '¿Qué valor genuino puede dar tu negocio?'
                        : mode === 'capsula' ? '¿Sobre qué tema quieres el dato sorprendente?'
                        : mode === 'trivia' ? '¿Sobre qué área será la pregunta?'
                        : mode === 'historia' ? '¿Qué problema resuelve tu negocio?'
                        : mode === 'alerta' ? '¿Cuál es el tema de la alerta?'
                        : mode === 'estacional' ? '¿Qué ángulo de tu negocio esta temporada?'
                        : '¿Qué quieres anunciar?'}
                    </label>
                    <textarea rows={2}
                      placeholder={
                        mode === 'comunitaria' ? 'Ej: Restaurante vegano — tips de alimentación saludable'
                        : mode === 'capsula' ? 'Ej: farmacia — datos curiosos de salud'
                        : mode === 'trivia' ? 'Ej: cocina mexicana, historia, salud'
                        : mode === 'historia' ? 'Ej: dolor de espalda, falta de tiempo para cocinar'
                        : mode === 'alerta' ? 'Ej: temporada de lluvias, calor extremo, quincena'
                        : mode === 'estacional' ? 'Ej: regreso a clases, ofertas de fin de año'
                        : 'Ej: Gran remate de zapatos, 50% de descuento sólo este sábado'
                      }
                      value={intent} onChange={(e) => setIntent(e.target.value)}
                      className="w-full rounded-lg border border-gray-300 px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none resize-none" />
                    {mode === 'comunitaria' && (
                      <p className="mt-1 text-xs text-green-700 bg-green-50 rounded-lg px-3 py-2">
                        🌿 El guión primero dará un consejo útil relacionado con tu categoría, luego mencionará tu negocio con honestidad — como la radio que educaba antes de vender.
                      </p>
                    )}
                    {mode === 'capsula' && (
                      <p className="mt-1 text-xs text-amber-700 bg-amber-50 rounded-lg px-3 py-2">
                        💡 Un dato real y sorprendente que el oyente no esperaba saber, seguido de la mención natural de tu negocio.
                      </p>
                    )}
                    {mode === 'trivia' && (
                      <p className="mt-1 text-xs text-purple-700 bg-purple-50 rounded-lg px-3 py-2">
                        🧠 Pregunta curiosa → el oyente responde por WhatsApp → interacción natural con tu negocio.
                      </p>
                    )}
                    {mode === 'historia' && (
                      <p className="mt-1 text-xs text-blue-700 bg-blue-50 rounded-lg px-3 py-2">
                        📖 Mini radionovela de 30s: un personaje con un problema real y tu negocio como la solución creíble.
                      </p>
                    )}
                    {mode === 'alerta' && (
                      <p className="mt-1 text-xs text-red-700 bg-red-50 rounded-lg px-3 py-2">
                        🚨 Información oportuna que el oyente necesita HOY, conectada naturalmente con tu negocio.
                      </p>
                    )}
                    {mode === 'estacional' && (
                      <p className="mt-1 text-xs text-teal-700 bg-teal-50 rounded-lg px-3 py-2">
                        🗓️ El mensaje correcto en el momento correcto — conecta tu negocio con lo que la gente ya está viviendo.
                      </p>
                    )}
                  </div>

                  {/* Extra context — trivia (premio), alerta/estacional (fecha/temporada) */}
                  {(mode === 'trivia' || mode === 'alerta' || mode === 'estacional') && (
                    <div>
                      <label className="mb-1.5 block text-sm font-medium text-gray-700">
                        {mode === 'trivia' ? '🎁 Premio mencionado en la trivia'
                          : mode === 'alerta' ? '📅 Contexto actual (fecha, clima, evento)'
                          : '📅 Temporada o momento del año'}
                      </label>
                      <input type="text"
                        placeholder={
                          mode === 'trivia' ? 'Ej: un 20% de descuento en tu próxima compra'
                          : mode === 'alerta' ? 'Ej: Temporada de lluvias en Guadalajara'
                          : 'Ej: Regreso a clases, Navidad, quincena'
                        }
                        value={extraContext} onChange={(e) => setExtraContext(e.target.value)}
                        className="w-full rounded-lg border border-gray-300 px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none" />
                    </div>
                  )}

                  {/* Categoría del negocio (para elegir jingle y contextualizar) */}
                  <div>
                    <label className="mb-1.5 block text-sm font-medium text-gray-700">Categoría del negocio (opcional)</label>
                    <input type="text" placeholder="Ej: farmacia, restaurante, gimnasio, inmobiliaria..."
                      value={businessCategory} onChange={(e) => setBusinessCategory(e.target.value)}
                      className="w-full rounded-lg border border-gray-300 px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none" />
                  </div>

                  <div>
                    <label className="mb-1.5 block text-sm font-medium text-gray-700">País / acento del locutor</label>
                    <select value={radioCountry} onChange={(e) => setRadioCountry(e.target.value)}
                      className="w-full rounded-lg border border-gray-300 px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none">
                      <option value="mx">🇲🇽 México</option>
                      <option value="co">🇨🇴 Colombia</option>
                      <option value="ar">🇦🇷 Argentina</option>
                      <option value="es">🇪🇸 España</option>
                    </select>
                  </div>
                  {!radioAudioUrl && (
                    <p className="text-xs text-gray-400">
                      Claude escribe el guión → voz de locutor → audio .ogg listo para WhatsApp {MODE_BADGE[mode]?.split(' ')[0] || '🎙️'}
                    </p>
                  )}
                  {radioAudioUrl && (
                    <div className="rounded-xl border border-green-200 bg-green-50 p-4 space-y-2">
                      <p className="text-sm font-medium text-green-700">
                        {MODE_BADGE[mode] || '✅'} Cuña generada
                      </p>
                      <audio controls src={radioAudioUrl} className="w-full" />
                      {radioScript && (
                        <details className="text-xs text-gray-500">
                          <summary className="cursor-pointer font-medium">Ver guión</summary>
                          <p className="mt-2 whitespace-pre-wrap">{radioScript}</p>
                        </details>
                      )}
                    </div>
                  )}
                </div>
              )}

              {/* Botón generar */}
              {!isRadioMode && (
                <button onClick={generateContent}
                  disabled={generating || !form.name || (mode !== 'saga' && !intent) || (mode === 'saga' && !productDesc)}
                  className="flex items-center gap-2 rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-60 transition-colors">
                  <Sparkles className="h-3.5 w-3.5" />
                  {generating ? 'Generando con Claude...' : mode === 'regular' ? 'Generar 3 variantes' : mode === 'sequence' ? 'Generar secuencia' : 'Generar saga'}
                </button>
              )}
              {isRadioMode && (
                <button onClick={generateContent}
                  disabled={generating || !form.name || !intent}
                  className="flex items-center gap-2 rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-60 transition-colors">
                  <Radio className="h-3.5 w-3.5" />
                  {generating ? 'Generando cuña...' : radioAudioUrl ? `Regenerar ${MODE_BADGE[mode] || 'cuña'}` : `Generar ${MODE_BADGE[mode] || 'cuña de radio'}`}
                </button>
              )}

              {/* Variantes — modo regular */}
              {mode === 'regular' && variants.length > 0 && (
                <div className="space-y-2">
                  <p className="text-sm font-medium text-gray-700">Selecciona una variante:</p>
                  {variants.map((v, i) => (
                    <button key={i} onClick={() => setForm({ ...form, message_text: v })}
                      className={`w-full rounded-lg border p-3 text-left text-sm transition-all ${form.message_text === v ? 'border-brand-500 bg-brand-50 text-brand-700' : 'border-gray-200 hover:border-brand-300 hover:bg-gray-50'}`}>
                      {v}
                    </button>
                  ))}
                </div>
              )}

              {/* Preview — modo secuencia o saga */}
              {isMultiMode && multiMessages.length > 0 && (
                <div className="space-y-2">
                  <p className="text-sm font-medium text-gray-700">
                    {mode === 'sequence' ? '📻 Secuencia generada (3 mensajes)' : '🎭 Saga generada (4 episodios)'}
                  </p>
                  {multiMessages.map((msg, i) => (
                    <div key={i} className="rounded-lg border border-gray-200 bg-gray-50 p-3">
                      <p className="mb-1 text-xs font-medium text-gray-500">
                        {mode === 'sequence' ? `Día ${[1, 3, 5][i] ?? i + 1}` : `Semana ${i + 1}`}
                      </p>
                      <textarea rows={3} value={msg}
                        onChange={(e) => {
                          const updated = [...multiMessages]
                          updated[i] = e.target.value
                          setMultiMessages(updated)
                        }}
                        className="w-full rounded border border-gray-200 bg-white px-2.5 py-2 text-sm focus:border-brand-500 focus:outline-none resize-none" />
                    </div>
                  ))}
                </div>
              )}

              {/* Mensaje final — solo en regular */}
              {mode === 'regular' && (
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-gray-700">Mensaje final</label>
                  <textarea rows={3} placeholder="El mensaje que recibirán tus clientes..."
                    value={form.message_text} onChange={(e) => setForm({ ...form, message_text: e.target.value })}
                    className="w-full rounded-lg border border-gray-300 px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none resize-none" />
                </div>
              )}

              {/* Cupón */}
              <div className={`rounded-xl border p-4 transition-all ${hasCoupon ? 'border-amber-300 bg-amber-50' : 'border-gray-200'}`}>
                <label className="flex cursor-pointer items-center gap-2">
                  <input type="checkbox" checked={hasCoupon} onChange={(e) => setHasCoupon(e.target.checked)}
                    className="h-4 w-4 rounded border-gray-300 text-amber-500" />
                  <span className="text-sm font-medium text-gray-700">🎫 Incluir cupón con expiración</span>
                </label>
                {hasCoupon && (
                  <div className="mt-3 grid grid-cols-2 gap-3">
                    <div>
                      <label className="mb-1 block text-xs font-medium text-gray-600">Descripción del cupón</label>
                      <input type="text" placeholder="Ej: 20% de descuento"
                        value={couponDesc} onChange={(e) => setCouponDesc(e.target.value)}
                        className="w-full rounded-lg border border-amber-200 px-3 py-2 text-sm focus:border-amber-400 focus:outline-none" />
                    </div>
                    <div>
                      <label className="mb-1 block text-xs font-medium text-gray-600">Válido por (horas)</label>
                      <select value={couponHours} onChange={(e) => setCouponHours(Number(e.target.value))}
                        className="w-full rounded-lg border border-amber-200 px-3 py-2 text-sm focus:border-amber-400 focus:outline-none">
                        <option value={24}>24 horas</option>
                        <option value={48}>48 horas</option>
                        <option value={72}>72 horas</option>
                        <option value={168}>1 semana</option>
                      </select>
                    </div>
                  </div>
                )}
              </div>

              {/* Programación */}
              <div className="rounded-xl border border-blue-100 bg-blue-50 p-4">
                <label className="mb-2 flex items-center gap-2 text-sm font-medium text-blue-800">
                  <CalendarClock className="h-4 w-4" />
                  Programar envío (opcional)
                </label>
                <input
                  type="datetime-local"
                  value={scheduledAt}
                  min={new Date().toISOString().slice(0, 16)}
                  onChange={(e) => setScheduledAt(e.target.value)}
                  className="w-full rounded-lg border border-blue-200 bg-white px-3 py-2 text-sm focus:border-blue-400 focus:outline-none"
                />
                {scheduledAt && (
                  <p className="mt-1.5 text-xs text-blue-600">
                    La campaña se enviará el {new Date(scheduledAt).toLocaleString('es-MX', { dateStyle: 'long', timeStyle: 'short' })}
                  </p>
                )}
              </div>

              {error && <p className="text-sm text-red-600">{error}</p>}
            </div>

            <div className="mt-5 flex gap-3">
              <button onClick={() => { setShowCreate(false); resetForm() }}
                className="flex-1 rounded-lg border border-gray-300 py-2.5 text-sm text-gray-700 hover:bg-gray-50">
                Cancelar
              </button>
              <button onClick={handleCreate}
                disabled={createMutation.isPending || !readyToCreate}
                className="flex-1 rounded-lg bg-brand-500 py-2.5 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-60">
                {createMutation.isPending ? 'Creando...' : scheduledAt ? 'Programar campaña' : 'Crear campaña'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Parrilla Semanal Modal */}
      {showParrilla && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={() => setShowParrilla(false)}>
          <div className="w-full max-w-5xl rounded-2xl bg-white p-6 shadow-2xl max-h-[92vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <div className="mb-5 flex items-center justify-between border-b pb-4">
              <div>
                <h3 className="text-xl font-bold text-gray-900 flex items-center gap-2">
                  <CalendarRange className="h-5 w-5 text-brand-500" />
                  Parrilla Semanal de Radio
                </h3>
                <p className="mt-1 text-sm text-gray-500">
                  Genera 7 días de contenido en un clic. Una estrategia completa para tus clientes.
                </p>
              </div>
              <button onClick={() => setShowParrilla(false)} className="text-gray-400 hover:text-gray-600">
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Formulario Izquierdo */}
              <div className="col-span-1 space-y-4 border-r pr-6">
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-gray-700">Nombre del negocio</label>
                  <input type="text" placeholder="Ej: Pizzería Don Corleone"
                    value={parrillaBusinessName} onChange={(e) => setParrillaBusinessName(e.target.value)}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none" />
                </div>
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-gray-700">Propósito principal de la semana</label>
                  <textarea rows={3} placeholder="Ej: Anunciar nuestras nuevas pizzas veganas y la promo del 2x1 los jueves"
                    value={parrillaIntent} onChange={(e) => setParrillaIntent(e.target.value)}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none resize-none" />
                </div>
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-gray-700">Categoría (opcional)</label>
                  <input type="text" placeholder="Ej: restaurante, zapatería"
                    value={parrillaCategory} onChange={(e) => setParrillaCategory(e.target.value)}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none" />
                </div>
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-gray-700">Contexto extra (opcional)</label>
                  <input type="text" placeholder="Ej: Premio de la trivia, temporada"
                    value={parrillaContext} onChange={(e) => setParrillaContext(e.target.value)}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none" />
                </div>
                <div className="rounded-xl border border-blue-100 bg-blue-50 p-4 space-y-3">
                  <label className="flex cursor-pointer items-start gap-2">
                    <input type="checkbox" checked={parrillaAutoSchedule} onChange={(e) => setParrillaAutoSchedule(e.target.checked)}
                      className="mt-0.5 h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500" />
                    <div>
                      <span className="text-sm font-medium text-blue-900">Programar envíos automáticos</span>
                      <p className="text-xs text-blue-700">Si está activo, se enviará cada día automáticamente a la hora elegida.</p>
                    </div>
                  </label>
                  {parrillaAutoSchedule && (
                    <div>
                      <label className="mb-1 block text-xs font-medium text-blue-800">Hora de envío local</label>
                      <input type="time" value={parrillaSendTime} onChange={(e) => setParrillaSendTime(e.target.value)}
                        className="w-full rounded border border-blue-200 px-2 py-1.5 text-sm" />
                    </div>
                  )}
                </div>

                {parrillaError && <p className="text-sm text-red-600">{parrillaError}</p>}

                <button onClick={generateParrilla}
                  disabled={parrillaGenerating || !parrillaBusinessName || !parrillaIntent}
                  className="w-full flex items-center justify-center gap-2 rounded-lg bg-brand-500 py-2.5 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-60 transition-colors">
                  <Sparkles className="h-4 w-4" />
                  {parrillaGenerating ? 'Generando 7 días...' : 'Generar Parrilla'}
                </button>
              </div>

              {/* Vista previa Derecha */}
              <div className="col-span-2">
                {!parrillaResult && !parrillaGenerating && (
                  <div className="flex h-full flex-col items-center justify-center rounded-xl border border-dashed border-gray-300 bg-gray-50 py-12 text-center">
                    <CalendarRange className="h-12 w-12 text-gray-300 mb-3" />
                    <p className="text-sm font-medium text-gray-500">Llena los datos y haz clic en Generar</p>
                    <p className="mt-1 text-xs text-gray-400">Crearemos 7 cuñas distintas optimizadas para cada día.</p>
                  </div>
                )}
                {parrillaGenerating && (
                  <div className="flex h-full flex-col items-center justify-center rounded-xl bg-gray-50 py-12 text-center">
                    <div className="h-8 w-8 animate-spin rounded-full border-4 border-brand-200 border-t-brand-500 mb-4" />
                    <p className="text-sm font-medium text-gray-700">Escribiendo y grabando 7 cuñas...</p>
                    <p className="mt-1 text-xs text-gray-500">Esto puede tardar un poco (Claude + Text-to-Speech)</p>
                  </div>
                )}
                {parrillaResult && (
                  <div className="space-y-4">
                    <div className="flex items-center justify-between bg-green-50 px-4 py-3 rounded-lg border border-green-200">
                      <div className="flex items-center gap-2">
                        <CheckCircle2 className="h-5 w-5 text-green-600" />
                        <span className="text-sm font-medium text-green-800">
                          {parrillaResult.auto_scheduled ? '¡Parrilla generada y programada!' : '¡Parrilla generada!'}
                        </span>
                      </div>
                      <span className="text-xs font-semibold text-green-700 uppercase bg-green-200 px-2 py-0.5 rounded-full">
                        Plan {parrillaResult.plan}
                      </span>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-h-[500px] overflow-y-auto pr-2">
                      {parrillaResult.days.map((d) => (
                        <div key={d.day} className="rounded-xl border border-gray-200 bg-white p-3 shadow-sm flex flex-col">
                          <div className="flex items-center justify-between mb-2">
                            <span className="font-semibold text-gray-800">{d.day_name}</span>
                            <span className="text-xs font-medium text-gray-500 flex items-center gap-1 bg-gray-100 px-2 py-0.5 rounded-full">
                              {d.mode_emoji} {MODE_BADGE[d.mode]?.replace(/[^a-zA-Z\s]/g, '').trim()}
                            </span>
                          </div>
                          {d.audio_url ? (
                            <audio controls src={d.audio_url} className="w-full h-8 mb-2" />
                          ) : (
                            <div className="flex items-center gap-1 text-xs text-red-500 mb-2 bg-red-50 p-1 rounded">
                              <AlertCircle className="h-3 w-3" /> Error al generar audio
                            </div>
                          )}
                          <div className="text-xs text-gray-600 bg-gray-50 p-2 rounded border border-gray-100 flex-1 overflow-y-auto max-h-24">
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
      )}

      {/* Analytics Modal */}
      {analyticsTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={() => setAnalyticsId(null)}>
          <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="mb-5 flex items-center justify-between">
              <div>
                <h3 className="font-semibold text-gray-900">{analyticsTarget.name}</h3>
                <span className={`mt-1 inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_COLORS[analyticsTarget.status] ?? 'bg-gray-100 text-gray-600'}`}>
                  {STATUS_LABELS[analyticsTarget.status] ?? analyticsTarget.status}
                </span>
              </div>
              <button onClick={() => setAnalyticsId(null)} className="text-gray-400 hover:text-gray-600">
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* Stat rows */}
            {(() => {
              const s = analyticsTarget.stats
              const sent = s.sent ?? 0
              const rows = [
                { label: 'Enviados', value: sent, color: 'bg-blue-400', pct: 100 },
                { label: 'Entregados', value: s.delivered ?? 0, color: 'bg-green-400', pct: sent > 0 ? ((s.delivered ?? 0) / sent) * 100 : 0 },
                { label: 'Leídos', value: s.read ?? 0, color: 'bg-indigo-400', pct: sent > 0 ? ((s.read ?? 0) / sent) * 100 : 0 },
                { label: 'Respondidos', value: s.replied ?? 0, color: 'bg-brand-500', pct: sent > 0 ? ((s.replied ?? 0) / sent) * 100 : 0 },
                { label: 'Fallidos', value: s.failed ?? 0, color: 'bg-red-400', pct: sent > 0 ? ((s.failed ?? 0) / sent) * 100 : 0 },
                { label: 'Cupones canjeados', value: s.coupons_redeemed ?? 0, color: 'bg-amber-400', pct: sent > 0 ? ((s.coupons_redeemed ?? 0) / sent) * 100 : 0 },
              ]
              return (
                <div className="space-y-3">
                  {rows.map((r) => (
                    <div key={r.label}>
                      <div className="mb-1 flex items-center justify-between text-sm">
                        <span className="text-gray-600">{r.label}</span>
                        <span className="font-semibold text-gray-900">
                          {r.value.toLocaleString()} {sent > 0 && r.label !== 'Enviados' && <span className="text-xs font-normal text-gray-400">({Math.round(r.pct)}%)</span>}
                        </span>
                      </div>
                      <div className="h-2 w-full overflow-hidden rounded-full bg-gray-100">
                        <div className={`h-full rounded-full transition-all ${r.color}`} style={{ width: `${Math.min(100, r.pct)}%` }} />
                      </div>
                    </div>
                  ))}
                </div>
              )
            })()}

            {analyticsTarget.schedule?.start_date && (
              <p className="mt-4 text-xs text-gray-400">
                Programada para {new Date(analyticsTarget.schedule.start_date).toLocaleString('es-MX', { dateStyle: 'long', timeStyle: 'short' })}
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
