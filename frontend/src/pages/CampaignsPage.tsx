import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api, { getApiError } from '@/lib/api'
import { Megaphone, Plus, Play, Pause, Trash2, Sparkles, Radio, CalendarClock, BarChart2, X, CalendarRange, CheckCircle2, AlertCircle, Download, ChevronLeft, ChevronRight, Loader2 } from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import SEO from '@/components/SEO'
import PrintButton from '@/components/PrintButton'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'

interface Campaign {
  id: string
  name: string
  type: string
  message_text: string
  status: string
  stats: Record<string, number>
  message_counts: Record<string, number>
  ab_test: Record<string, any>
  created_at: string
  schedule?: { start_date?: string; end_date?: string } | null
}

const CAMPAIGN_TYPES = [
  { value: 'promo', label: '🎁 Promoción' },
  { value: 'reminder', label: '⏰ Recordatorio' },
  { value: 'launch', label: '🚀 Lanzamiento' },
  { value: 'event', label: '🎉 Evento' },
  { value: 'voces', label: '🎤 Voces del Barrio' },
]

// Modos de campaña — La Nueva Radio
const CAMPAIGN_MODES = [
  { value: 'regular', label: '📢 Regular', desc: 'Un mensaje personalizado con nombre y ciudad' },
  { value: 'banner', label: '🖼️ Banner Visual', desc: 'Imagen personalizada con el nombre del contacto — IA genera el diseño' },
  { value: 'sequence', label: '📻 Secuencia', desc: '3 mensajes en días 1, 3 y 5 — como un programa de radio' },
  { value: 'saga', label: '🎭 Saga', desc: '4 episodios semanales — radionovela de tu negocio' },
  { value: 'radio', label: '🎙️ Cuña clásica', desc: 'Audio estilo radio AM/FM de los 80s con voz de locutor' },
  { value: 'comunitaria', label: '🌿 Radio Comunitaria', desc: 'Primero un consejo genuino, luego tu negocio' },
  { value: 'capsula', label: '💡 Cápsula del Día', desc: 'Dato sorprendente + mención natural del negocio' },
  { value: 'trivia', label: '🧠 Trivia del Día', desc: 'Pregunta curiosa + respuesta + negocio — perfecto para interacción' },
  { value: 'historia', label: '📖 Mini Historia', desc: 'Radionovela de 30s: personaje → problema → tu negocio como solución' },
  { value: 'alerta', label: '🚨 Alerta de Servicio', desc: 'Info contextual oportuna (clima, fecha) + tu negocio' },
  { value: 'estacional', label: '🗓️ Cuña Estacional', desc: 'Conecta tu negocio con el momento exacto del año' },
  { value: 'voces', label: '🎤 Voces del Barrio', desc: 'Colecciona audios reales de clientes y genera una cápsula narrativa con IA' },
]

const STATUS_COLORS: Record<string, string> = {
  draft: 'bg-muted text-gray-600 dark:bg-gray-800 dark:text-gray-400',
  scheduled: 'bg-blue-100 text-blue-600 dark:bg-blue-900/50 dark:text-blue-300',
  running: 'bg-green-100 text-green-600 dark:bg-green-900/50 dark:text-green-300',
  paused: 'bg-yellow-100 text-yellow-600 dark:bg-yellow-900/50 dark:text-yellow-300',
  completed: 'bg-purple-100 text-purple-600 dark:bg-purple-900/50 dark:text-purple-300',
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
  banner: '🖼️ Banner Visual',
  voces: '🎤 Voces del Barrio',
}

type CampaignMode = 'regular' | 'banner' | 'sequence' | 'saga' | 'radio' | 'comunitaria' | 'capsula' | 'trivia' | 'historia' | 'alerta' | 'estacional' | 'voces'

const AUDIO_MODES: CampaignMode[] = ['radio', 'comunitaria', 'capsula', 'trivia', 'historia', 'alerta', 'estacional']

export default function CampaignsPage() {
  const qc = useQueryClient()
  const { user: currentUser } = useAuth()
  const { toast } = useToast()
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
  const [radioVoiceId, setRadioVoiceId] = useState('')
  const [scheduledAt, setScheduledAt] = useState('')
  const [error, setError] = useState('')
  const [abEnabled, setAbEnabled] = useState(false)
  const [abVariants, setAbVariants] = useState<string[]>(['', ''])
  const [abSplit, setAbSplit] = useState('50/50')
  const [abMetric, setAbMetric] = useState('response')
  const [analyticsId, setAnalyticsId] = useState<string | null>(null)
  const [vocesDetailId, setVocesDetailId] = useState<string | null>(null)
  const [page, setPage] = useState(1)

  // Banner Visual mode
  const [bannerPromo, setBannerPromo] = useState('')
  const [bannerPalette, setBannerPalette] = useState('promo')
  const [bannerLayout, setBannerLayout] = useState('clasico')
  const [bannerCaption, setBannerCaption] = useState('')
  const [bannerPreviewUrl, setBannerPreviewUrl] = useState<string | null>(null)
  const [bannerPreviewing, setBannerPreviewing] = useState(false)

  // Voces del Barrio
  const [vocesCollectionPrompt, setVocesCollectionPrompt] = useState('')
  const [vocesStories, setVocesStories] = useState<{ id: string; transcription: string; sentiment: string; approved: boolean; contact_name?: string; created_at: string }[]>([])
  const [vocesCapsuleAudioUrl, setVocesCapsuleAudioUrl] = useState('')
  const [vocesCapsuleScript, setVocesCapsuleScript] = useState('')
  const [vocesGenerating, setVocesGenerating] = useState(false)

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

  const { data: campaignsData, isLoading } = useQuery<{ items: Campaign[]; total: number }>({
    queryKey: ['campaigns', page],
    queryFn: () => api.get('/campaigns', { params: { page, page_size: 20 } }).then((r) => r.data),
  })

  const campaigns = campaignsData?.items
  const totalCampaigns = campaignsData?.total ?? 0
  const totalPages = totalCampaigns > 0 ? Math.ceil(totalCampaigns / 20) : 0

  function getPageNumbers() {
    const pages: (number | string)[] = [1]
    if (totalPages <= 1) return pages
    const delta = 1
    const rangeStart = Math.max(2, page - delta)
    const rangeEnd = Math.min(totalPages - 1, page + delta)
    if (rangeStart > 2) pages.push('...')
    for (let i = rangeStart; i <= rangeEnd; i++) pages.push(i)
    if (rangeEnd < totalPages - 1) pages.push('...')
    if (totalPages > 1) pages.push(totalPages)
    return pages
  }

  interface Template { id: string; name: string; content: string; category: string | null }
  interface Voice { id: string; name: string; lang: string; gender: string; provider: string }
  const { data: templatesData } = useQuery<Template[]>({
    queryKey: ['templates'],
    queryFn: () => api.get('/templates').then((r) => r.data),
    staleTime: 1000 * 60 * 5,
  })
  const { data: voicesData } = useQuery<Voice[]>({
    queryKey: ['radio-voices'],
    queryFn: () => api.get('/radio/voices').then((r) => r.data),
    staleTime: 1000 * 60 * 60,
  })

  const { data: optimalTime } = useQuery<{ best_window: string; best_hour: number }>({
    queryKey: ['optimal-send-time'],
    queryFn: () => api.get('/analytics/optimal-send-time').then((r) => r.data),
    staleTime: 1000 * 60 * 30,
  })

  const createMutation = useMutation({
    mutationFn: (body: object) => api.post('/campaigns', body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['campaigns'] }); qc.invalidateQueries({ queryKey: ['dashboard'] }); setShowCreate(false); resetForm() },
    onError: (err: unknown) => setError(getApiError(err)),
  })

  const pauseMutation = useMutation({
    mutationFn: (id: string) => api.post(`/campaigns/${id}/pause`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['campaigns'] }); qc.invalidateQueries({ queryKey: ['dashboard'] }) },
    onError: (err: unknown) => toast({ title: 'Error', description: getApiError(err, 'Error al pausar campaña'), variant: 'error' }),
  })
  const resumeMutation = useMutation({
    mutationFn: (id: string) => api.post(`/campaigns/${id}/resume`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['campaigns'] }); qc.invalidateQueries({ queryKey: ['dashboard'] }) },
    onError: (err: unknown) => toast({ title: 'Error', description: getApiError(err, 'Error al iniciar campaña'), variant: 'error' }),
  })
  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/campaigns/${id}`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['campaigns'] }); qc.invalidateQueries({ queryKey: ['dashboard'] }) },
  })

  const resetForm = () => {
    setForm({ name: '', type: 'promo', message_text: '' })
    setMode('regular'); setVariants([]); setMultiMessages([])
    setIntent(''); setProductDesc(''); setProtagonist('María')
    setHasCoupon(false); setCouponDesc(''); setCouponHours(72)
    setRadioCountry('mx'); setRadioAudioUrl(''); setRadioScript('')
    setExtraContext(''); setBusinessCategory(''); setRadioVoiceId('')
    setScheduledAt(''); setError('')
    setAbEnabled(false); setAbVariants(['', '']); setAbSplit('50/50'); setAbMetric('response')
    setBannerPromo(''); setBannerPalette('promo'); setBannerLayout('clasico'); setBannerCaption(''); setBannerPreviewUrl(null)
    setVocesCollectionPrompt(''); setVocesStories([]); setVocesCapsuleAudioUrl(''); setVocesCapsuleScript('')
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
          voice_id: radioVoiceId || undefined,
        })
        setRadioAudioUrl(data.audio_url)
        setRadioScript(data.script ?? '')
      }
    } catch (err: unknown) {
      setError(getApiError(err, 'Error al generar contenido'))
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
      }, { timeout: 120000 })
      setParrillaResult(data)
    } catch (err: unknown) {
      setParrillaError(getApiError(err, 'Error al generar parrilla'))
    } finally {
      setParrillaGenerating(false)
    }
  }

  const handleCreate = () => {
    const ab_test: Record<string, unknown> = {
      campaign_mode: mode,
      has_coupon: hasCoupon,
      coupon_description: couponDesc,
      coupon_hours: couponHours,
    }
    if (mode !== 'regular' && multiMessages.length > 0) {
      ab_test.messages = multiMessages
    }
    if (abEnabled) {
      ab_test.enabled = true
      ab_test.variants = abVariants.filter(Boolean)
      ab_test.split = abSplit
      ab_test.metric = abMetric
    }
    if (AUDIO_MODES.includes(mode)) {
      ab_test.audio_url = radioAudioUrl
      ab_test.radio_script = radioScript
    }
    if (mode === 'banner') {
      ab_test.promo_description = bannerPromo
      ab_test.banner_palette = bannerPalette
      ab_test.banner_layout = bannerLayout
      ab_test.banner_caption = bannerCaption
    }
    const schedule = scheduledAt ? { start_date: new Date(scheduledAt).toISOString() } : {}
    const campaignStatus = scheduledAt ? 'scheduled' : 'draft'
    createMutation.mutate({
      ...form,
      message_text: form.message_text || radioScript || bannerPromo,
      ab_test,
      schedule,
      status: campaignStatus,
    })
  }

  const analyticsTarget = campaigns?.find((c) => c.id === analyticsId)
  const vocesDetailTarget = campaigns?.find((c) => c.id === vocesDetailId)
  const { data: storiesData, isLoading: storiesLoading, refetch: refetchStories } = useQuery({
    queryKey: ['campaign-stories', vocesDetailId],
    queryFn: () => api.get(`/campaigns/${vocesDetailId}/stories`).then((r) => r.data),
    enabled: !!vocesDetailId,
  })
  const [capsuleAudioUrl, setCapsuleAudioUrl] = useState('')
  const [capsuleScript, setCapsuleScript] = useState('')
  const [capsuleGenerating, setCapsuleGenerating] = useState(false)

  const approveStoryMutation = useMutation({
    mutationFn: (storyId: string) => api.patch(`/campaigns/stories/${storyId}/approve`),
    onSuccess: () => refetchStories(),
  })

  const isMultiMode = mode === 'sequence' || mode === 'saga'
  const isRadioMode = AUDIO_MODES.includes(mode)
  const isBannerMode = mode === 'banner'
  const isVocesMode = mode === 'voces'
  const readyToCreate = form.name && (
    (mode === 'regular' && form.message_text) ||
    (isMultiMode && multiMessages.length > 0) ||
    (isRadioMode && !!radioAudioUrl) ||
    (isBannerMode && !!bannerPromo) ||
    (isVocesMode && !!vocesCollectionPrompt)
  )

  const previewBanner = async () => {
    if (!bannerPromo) return
    setBannerPreviewing(true)
    setBannerPreviewUrl(null)
    try {
      const resp = await api.post('/campaigns/banner/preview', {
        promo_description: bannerPromo,
        business_name: form.name || 'Mi negocio',
        contact_name: 'Juan',
        palette: bannerPalette,
        layout: bannerLayout,
        business_category: currentUser?.business_category || '',
      }, { responseType: 'blob' })
      const url = URL.createObjectURL(resp.data)
      setBannerPreviewUrl(url)
    } catch {
      setError('Error generando preview del banner')
    } finally {
      setBannerPreviewing(false)
    }
  }

  return (
    <>
      <SEO title="Campañas" description="Panel de control de IaRadio." noIndex />
      <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Campañas</h1>
          <p className="mt-1 text-sm text-muted-foreground">{totalCampaigns} campañas creadas</p>
        </div>
        <div className="flex gap-3">
          <PrintButton />
          {(campaigns?.length ?? 0) > 0 && (
            <button
              onClick={async () => {
                try {
                  const response = await api.get('/campaigns/export-csv', { responseType: 'blob' })
                  const url = URL.createObjectURL(new Blob([response.data], { type: 'text/csv' }))
                  const a = document.createElement('a'); a.href = url; a.download = 'campanas_iaradio.csv'; a.click()
                  URL.revokeObjectURL(url)
                } catch { toast({ title: 'Error', description: 'Error al exportar', variant: 'error' }) }
              }}
              className="flex items-center gap-2 rounded-lg border border-border bg-card px-4 py-2 text-sm font-medium text-gray-700 hover:bg-muted transition-colors"
            >
              <Download className="h-4 w-4" /> Exportar CSV
            </button>
          )}
          <button
            onClick={() => setShowParrilla(true)}
            className="flex items-center gap-2 rounded-lg border border-border bg-card px-4 py-2 text-sm font-medium text-gray-700 hover:bg-muted transition-colors"
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

      <div className="print-area">
      {/* No credits warning */}
      {noCredits && (
        <div className="rounded-xl border border-orange-200 bg-orange-50 dark:bg-orange-950/30 px-5 py-4 flex items-center justify-between">
          <div>
            <p className="text-sm font-semibold text-orange-800 dark:text-orange-200">Sin mensajes disponibles</p>
            <p className="text-xs text-orange-600 dark:text-orange-300">Adquiere un plan para crear y enviar campañas.</p>
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
            <div key={i} className="h-24 rounded-xl bg-muted animate-pulse" />
          ))
        ) : campaigns?.length === 0 ? (
          <div className="flex flex-col items-center justify-center rounded-xl bg-card py-16 shadow-sm border border-border text-muted-foreground">
            <Radio className="h-12 w-12 mb-3" />
            <p className="text-sm font-medium">No hay campañas todavía</p>
            <p className="text-xs mt-1">Crea tu primera campaña — regular, secuencia o saga</p>
          </div>
        ) : (
          campaigns?.map((campaign) => (
            <div key={campaign.id} className="rounded-xl bg-card p-5 shadow-sm border border-border">
              <div className="flex items-start justify-between">
                <div className="flex-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="font-semibold text-foreground truncate">{campaign.name}</h3>
                    <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_COLORS[campaign.status] ?? 'bg-muted text-gray-600 dark:bg-gray-800 dark:text-gray-400'}`}>
                      {STATUS_LABELS[campaign.status] ?? campaign.status}
                    </span>
                    {campaign.ab_test?.campaign_mode && campaign.ab_test.campaign_mode !== 'regular' && (
                      <span className="rounded-full bg-purple-100 dark:bg-purple-900/50 px-2.5 py-0.5 text-xs font-medium text-purple-600 dark:text-purple-300">
                        {MODE_BADGE[campaign.ab_test.campaign_mode]}
                      </span>
                    )}
                    {campaign.ab_test?.has_coupon && (
                      <span className="rounded-full bg-amber-100 dark:bg-amber-900/50 px-2.5 py-0.5 text-xs font-medium text-amber-600 dark:text-amber-300">
                        🎫 Con cupón
                      </span>
                    )}
                  </div>
                  <p className="mt-1.5 text-sm text-muted-foreground line-clamp-2">{campaign.message_text}</p>
                  {campaign.ab_test?.audio_url && (
                    <div className="mt-3">
                      <audio controls src={campaign.ab_test.audio_url} className="h-8 w-full max-w-md rounded-lg" />
                    </div>
                  )}
                  <div className="mt-3 flex flex-wrap gap-3 text-xs text-muted-foreground">
                    <span>📤 {campaign.stats.sent ?? 0} enviados</span>
                    <span>✅ {campaign.stats.delivered ?? 0} entregados</span>
                    <span>💬 {campaign.stats.replied ?? 0} respondidos</span>
                    <span>🎫 {campaign.stats.coupons_redeemed ?? 0} canjeados</span>
                    {Object.keys(campaign.message_counts).length > 0 && (
                      <span title="Estado real de entrega por contacto" className="flex gap-2 ml-2 border-l border-border pl-2">
                        {campaign.message_counts.sent > 0 && <span className="text-blue-500">📤{campaign.message_counts.sent}</span>}
                        {campaign.message_counts.delivered > 0 && <span className="text-green-500">✅{campaign.message_counts.delivered}</span>}
                        {campaign.message_counts.read > 0 && <span className="text-violet-500">👁️{campaign.message_counts.read}</span>}
                        {campaign.message_counts.failed > 0 && <span className="text-red-500">❌{campaign.message_counts.failed}</span>}
                        {campaign.message_counts.queued > 0 && <span className="text-amber-500">⏳{campaign.message_counts.queued}</span>}
                      </span>
                    )}
                  </div>
                  {(campaign.stats.sent ?? 0) > 0 && (
                    <div className="mt-3 flex flex-wrap items-center gap-4">
                      {/* Delivery rate */}
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] text-muted-foreground whitespace-nowrap">Entrega</span>
                        <div className="h-1.5 w-20 overflow-hidden rounded-full bg-muted">
                          <div
                            className="h-full rounded-full bg-green-400 dark:bg-green-500 transition-all"
                            style={{ width: `${Math.min(100, Math.round(((campaign.stats.delivered ?? 0) / campaign.stats.sent) * 100))}%` }}
                          />
                        </div>
                        <span className="text-[10px] font-semibold text-green-600 dark:text-green-400">
                          {Math.round(((campaign.stats.delivered ?? 0) / campaign.stats.sent) * 100)}%
                        </span>
                      </div>
                      {/* Response rate */}
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] text-muted-foreground whitespace-nowrap">Respuesta</span>
                        <div className="h-1.5 w-20 overflow-hidden rounded-full bg-muted">
                          <div
                            className="h-full rounded-full bg-brand-500 dark:bg-brand-400 transition-all"
                            style={{ width: `${Math.min(100, Math.round(((campaign.stats.replied ?? 0) / campaign.stats.sent) * 100))}%` }}
                          />
                        </div>
                        <span className="text-[10px] font-semibold text-brand-600 dark:text-brand-400">
                          {Math.round(((campaign.stats.replied ?? 0) / campaign.stats.sent) * 100)}%
                        </span>
                      </div>
                    </div>
                  )}
                  {/* A/B Test Results */}
                  {campaign.ab_test?.enabled && (
                    <div className="mt-4 border-t border-purple-100 dark:border-purple-800 pt-3">
                      <p className="text-xs font-semibold text-purple-700 dark:text-purple-300 mb-2">🔬 Prueba A/B</p>
                      {(() => {
                        const variants = campaign.ab_test.variants || []
                        const statsA = campaign.ab_test.stats_a || { sent: 0, replied: 0 }
                        const statsB = campaign.ab_test.stats_b || { sent: 0, replied: 0 }
                        const statsC = campaign.ab_test.stats_c || { sent: 0, replied: 0 }
                        const allStats = [statsA, statsB]
                        if (statsC.sent > 0) allStats.push(statsC)
                        const chartData = allStats.map((s: { sent: number; replied: number }, i: number) => {
                          const label = String.fromCharCode(65 + i)
                          const responseRate = s.sent > 0 ? Math.round((s.replied / s.sent) * 100) : 0
                          return {
                            name: `Variante ${label}`,
                            sent: s.sent ?? 0,
                            rate: responseRate,
                            fill: i === 0 ? '#a855f7' : i === 1 ? '#6366f1' : '#ec4899',
                          }
                        })
                        const maxRate = Math.max(...chartData.map((d) => d.rate), 0)
                        return (
                          <div className="space-y-2">
                            <div className="h-24">
                              <ResponsiveContainer width="100%" height="100%">
                                <BarChart data={chartData} margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
                                  <XAxis dataKey="name" tick={{ fontSize: 10 }} />
                                  <YAxis tick={{ fontSize: 10 }} unit="%" domain={[0, 'auto']} />
                                  <Tooltip formatter={(v: number, name: string) => [name === 'rate' ? `${v}%` : v, name === 'rate' ? 'Respuesta' : 'Enviados']} />
                                  <Bar dataKey="rate" radius={[4, 4, 0, 0]} fill="#a855f7">
                                    {chartData.map((entry, i) => <Cell key={i} fill={entry.fill} />)}
                                  </Bar>
                                </BarChart>
                              </ResponsiveContainer>
                            </div>
                            <div className="flex gap-2 flex-wrap">
                              {chartData.map((d) => (
                                <div key={d.name} className="flex items-center gap-1.5 text-[11px] text-gray-600 dark:text-gray-400 bg-purple-50 dark:bg-purple-950/30 rounded-lg px-2 py-1">
                                  <span className="w-2 h-2 rounded-full" style={{ background: d.fill }} />
                                  {d.name}: {d.rate}% ({d.sent} enviados)
                                  {d.rate === maxRate && d.rate > 0 && (
                                    <span className="text-amber-600 font-bold ml-1">🏆</span>
                                  )}
                                </div>
                              ))}
                            </div>
                          </div>
                        )
                      })()}
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-2 ml-4 shrink-0 flex-wrap">
                  <button onClick={() => setAnalyticsId(campaign.id)}
                    className="rounded-lg border border-border p-1.5 text-muted-foreground hover:bg-muted transition-colors shrink-0">
                    <BarChart2 className="h-3.5 w-3.5" />
                  </button>
                  {campaign.type === 'voces' && (
                    <button onClick={() => setVocesDetailId(campaign.id)}
                      className="rounded-lg border border-purple-200 dark:border-purple-800 bg-purple-50 dark:bg-purple-950/30 p-1.5 text-purple-600 dark:text-purple-300 hover:bg-purple-100 transition-colors shrink-0">
                      <Megaphone className="h-3.5 w-3.5" />
                    </button>
                  )}
                  {campaign.status === 'running' && (
                    <button onClick={() => pauseMutation.mutate(campaign.id)}
                      disabled={pauseMutation.isPending}
                      className="rounded-lg border border-yellow-200 bg-yellow-50 dark:bg-yellow-950/30 p-1.5 text-yellow-600 dark:text-yellow-300 hover:bg-yellow-100 shrink-0 disabled:opacity-50">
                      {pauseMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Pause className="h-3.5 w-3.5" />}
                    </button>
                  )}
                  {(campaign.status === 'paused' || campaign.status === 'draft' || campaign.status === 'scheduled') && (
                    <button onClick={() => resumeMutation.mutate(campaign.id)}
                      disabled={resumeMutation.isPending}
                      title={campaign.status === 'draft' ? "Enviar campaña ahora" : campaign.status === 'scheduled' ? "Forzar envío ahora" : "Reanudar campaña"}
                      className="rounded-lg border border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-950/30 p-1.5 text-green-600 dark:text-green-300 hover:bg-green-100 transition-colors shrink-0 disabled:opacity-50">
                      {resumeMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
                    </button>
                  )}
                  <button onClick={() => { if (confirm('¿Eliminar esta campaña?')) deleteMutation.mutate(campaign.id) }}
                    className="text-muted-foreground hover:text-red-500 dark:hover:text-red-400 transition-colors shrink-0">
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Pagination */}
      {campaignsData && totalPages > 1 && (
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4 pt-1">
          <p className="text-sm text-muted-foreground">
            Mostrando {Math.min((page - 1) * 20 + 1, totalCampaigns)}-{Math.min(page * 20, totalCampaigns)} de {totalCampaigns} campañas
          </p>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1}
              className="rounded-lg border border-border p-2 text-muted-foreground hover:bg-muted disabled:opacity-50 disabled:cursor-not-allowed transition-colors dark:border-gray-800 dark:hover:bg-gray-900"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            {getPageNumbers().map((p, i) =>
              p === '...' ? (
                <span key={`ellipsis-${i}`} className="px-2 text-sm text-muted-foreground">...</span>
              ) : (
                <button
                  key={p}
                  onClick={() => setPage(p as number)}
                  className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
                    page === p
                      ? 'bg-brand-500 text-white'
                      : 'text-muted-foreground hover:bg-muted dark:hover:bg-gray-900'
                  }`}
                >
                  {p}
                </button>
              )
            )}
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages}
              className="rounded-lg border border-border p-2 text-muted-foreground hover:bg-muted disabled:opacity-50 disabled:cursor-not-allowed transition-colors dark:border-gray-800 dark:hover:bg-gray-900"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}

      {/* Create Modal */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 dark:bg-black/80 p-4">
          <div className="w-full max-w-2xl rounded-2xl bg-card p-6 shadow-2xl max-h-[92vh] overflow-y-auto">
            <h3 className="mb-5 text-lg font-semibold text-foreground">Nueva campaña</h3>

            <div className="space-y-4">
              {/* Template picker */}
              {(templatesData?.length ?? 0) > 0 && (
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">📋 Usar template guardado</label>
                  <select
                    defaultValue=""
                    onChange={(e) => {
                      const t = templatesData?.find((x) => x.id === e.target.value)
                      if (t) setForm({ ...form, message_text: t.content })
                    }}
                    className="w-full rounded-lg border border-border px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none"
                  >
                    <option value="">— Seleccionar template —</option>
                    {templatesData?.map((t) => (
                      <option key={t.id} value={t.id}>{t.name}{t.category ? ` (${t.category})` : ''}</option>
                    ))}
                  </select>
                </div>
              )}

              {/* Nombre + tipo */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">Nombre</label>
                  <input type="text" placeholder="Ej: Promo verano"
                    value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
                    className="w-full rounded-lg border border-border px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none" />
                </div>
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">Tipo</label>
                  <select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}
                    className="w-full rounded-lg border border-border px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none">
                    {CAMPAIGN_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
                  </select>
                </div>
              </div>

              {/* Modo de campaña — La Nueva Radio */}
              <div>
                <label className="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300">🎙️ Modo de campaña</label>
                <div className="grid grid-cols-2 gap-2">
                  {CAMPAIGN_MODES.map((m) => (
                    <button key={m.value} onClick={() => { setMode(m.value as CampaignMode); setVariants([]); setMultiMessages([]); setRadioAudioUrl(''); setRadioScript('') }}
                      className={`rounded-xl border p-3 text-left transition-all ${mode === m.value ? 'border-brand-500 bg-brand-50 dark:bg-brand-950/30' : 'border-border hover:border-brand-300'}`}>
                      <div className="text-sm font-medium text-foreground">{m.label}</div>
                      <div className="mt-0.5 text-xs text-muted-foreground">{m.desc}</div>
                    </button>
                  ))}
                </div>
              </div>

              {/* Inputs según modo */}
              {mode === 'regular' && (
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">¿Qué quieres comunicar?</label>
                  <textarea rows={2} placeholder="Ej: 30% de descuento este fin de semana"
                    value={intent} onChange={(e) => setIntent(e.target.value)}
                    className="w-full rounded-lg border border-border px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none resize-none" />
                  <p className="mt-1 text-xs text-muted-foreground">
                    Puedes usar <code>{'{{nombre}}'}</code>, <code>{'{{ciudad}}'}</code> en el mensaje para personalización automática
                  </p>
                </div>
              )}
              {mode === 'sequence' && (
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">¿Qué historia cuenta la secuencia?</label>
                  <textarea rows={2} placeholder="Ej: Lanzamiento de nuevos platillos de temporada"
                    value={intent} onChange={(e) => setIntent(e.target.value)}
                    className="w-full rounded-lg border border-border px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none resize-none" />
                  <p className="mt-1 text-xs text-muted-foreground">Claude creará 3 mensajes para días 1, 3 y 5</p>
                </div>
              )}
              {mode === 'saga' && (
                <div className="space-y-3">
                  <div>
                    <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">¿Qué producto/servicio protagoniza la saga?</label>
                    <textarea rows={2} placeholder="Ej: Clases de yoga para mamás con poco tiempo"
                      value={productDesc} onChange={(e) => setProductDesc(e.target.value)}
                      className="w-full rounded-lg border border-border px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none resize-none" />
                  </div>
                  <div>
                    <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">Nombre del protagonista</label>
                    <input type="text" value={protagonist} onChange={(e) => setProtagonist(e.target.value)}
                      className="w-full rounded-lg border border-border px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none" />
                  </div>
                  <p className="text-xs text-muted-foreground">Claude creará 4 episodios semanales al estilo radionovela 📻</p>
                </div>
              )}
              {/* ── Banner Visual mode ─────────────────────────────────── */}
              {isBannerMode && (
                <div className="space-y-4">
                  <div>
                    <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">¿Qué quieres promocionar?</label>
                    <textarea rows={2}
                      placeholder="Ej: 20% de descuento esta semana en todos los productos, solo por tiempo limitado"
                      value={bannerPromo} onChange={(e) => setBannerPromo(e.target.value)}
                      className="w-full rounded-lg border border-border px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none resize-none" />
                    <p className="mt-1 text-xs text-indigo-700 bg-indigo-50 dark:bg-indigo-950/30 rounded-lg px-3 py-2">
                      🎨 La IA generará el copy del banner y diseñará la imagen. Cada contacto recibirá su nombre dentro de la foto.
                    </p>
                  </div>

                  <div>
                    <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">Paleta de colores</label>
                    <div className="grid grid-cols-4 gap-2">
                      {[
                        { key: 'promo', label: 'Azul/Rojo', colors: ['#1d3557', '#e63946'] },
                        { key: 'verde', label: 'Verde', colors: ['#1b5e20', '#388e3c'] },
                        { key: 'oscuro', label: 'Negro/Neón', colors: ['#121212', '#00e676'] },
                        { key: 'elegante', label: 'Dorado', colors: ['#1a1a2e', '#e8c547'] },
                        { key: 'naranja', label: 'Naranja', colors: ['#e65100', '#ff8f00'] },
                        { key: 'morado', label: 'Morado', colors: ['#4a148c', '#7b1fa2'] },
                        { key: 'azul', label: 'Azul vivo', colors: ['#0d47a1', '#1565c0'] },
                        { key: 'rojo', label: 'Rojo', colors: ['#b71c1c', '#e53935'] },
                      ].map((p) => (
                        <button key={p.key} onClick={() => { setBannerPalette(p.key); setBannerPreviewUrl(null) }}
                          className={`flex items-center gap-2 rounded-lg border-2 px-2 py-1.5 text-xs font-medium transition ${bannerPalette === p.key ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-950/30' : 'border-border hover:border-brand-300'}`}>
                          <span className="flex gap-0.5">
                            {p.colors.map((c, i) => (
                              <span key={i} className="w-3 h-3 rounded-full inline-block" style={{ background: c }} />
                            ))}
                          </span>
                          {p.label}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div>
                    <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">Diseño del banner</label>
                    <div className="grid grid-cols-4 gap-2">
                      {[
                        { key: 'clasico', label: 'Clásico', desc: 'Izquierda, CTA abajo' },
                        { key: 'centrado', label: 'Centrado', desc: 'Todo al centro' },
                        { key: 'split', label: 'Split', desc: 'Mitad y mitad' },
                        { key: 'minimal', label: 'Minimal', desc: 'Elegante, sutil' },
                      ].map((l) => (
                        <button key={l.key} onClick={() => { setBannerLayout(l.key); setBannerPreviewUrl(null) }}
                          className={`rounded-lg border-2 px-2 py-2 text-xs font-medium transition ${bannerLayout === l.key ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-950/30' : 'border-border hover:border-brand-300'}`}>
                          <div className="font-semibold">{l.label}</div>
                          <div className="text-[10px] text-muted-foreground mt-0.5">{l.desc}</div>
                        </button>
                      ))}
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground">Se usa automáticamente según tu categoría de negocio si no eliges uno.</p>
                  </div>

                  <div>
                    <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">Texto del mensaje (opcional)</label>
                    <input type="text"
                      placeholder="Ej: ¡Hola! Mira lo que tenemos para ti 👆"
                      value={bannerCaption} onChange={(e) => setBannerCaption(e.target.value)}
                      className="w-full rounded-lg border border-border px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none" />
                    <p className="mt-1 text-xs text-muted-foreground">Este texto se envía junto con la imagen. Si lo dejas vacío se genera automáticamente.</p>
                  </div>

                  {/* Preview */}
                  <div className="space-y-2">
                    <button onClick={previewBanner} disabled={!bannerPromo || bannerPreviewing}
                      className="flex items-center gap-2 rounded-lg border border-indigo-300 bg-indigo-50 dark:bg-indigo-950/30 px-4 py-2 text-sm font-medium text-indigo-700 hover:bg-indigo-100 disabled:opacity-50 transition">
                      {bannerPreviewing ? (
                        <><span className="h-4 w-4 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" />Generando preview...</>
                      ) : (
                        <>🖼️ Ver preview del banner</>
                      )}
                    </button>
                    {bannerPreviewUrl && (
                      <div className="rounded-xl overflow-hidden border border-border shadow-sm">
                        <img src={bannerPreviewUrl} alt="Preview banner" className="w-full max-h-80 object-cover" />
                        <p className="text-center text-xs text-muted-foreground py-2 bg-muted">
                          Preview con nombre "Juan" — cada contacto verá su propio nombre
                        </p>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {isRadioMode && (
                <div className="space-y-3">                  <div>
                    <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">
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
                      className="w-full rounded-lg border border-border px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none resize-none" />
                    {mode === 'comunitaria' && (
                      <p className="mt-1 text-xs text-green-700 dark:text-green-300 bg-green-50 dark:bg-green-950/30 rounded-lg px-3 py-2">
                        🌿 El guión primero dará un consejo útil relacionado con tu categoría, luego mencionará tu negocio con honestidad — como la radio que educaba antes de vender.
                      </p>
                    )}
                    {mode === 'capsula' && (
                      <p className="mt-1 text-xs text-amber-700 dark:text-amber-300 bg-amber-50 dark:bg-amber-950/30 rounded-lg px-3 py-2">
                        💡 Un dato real y sorprendente que el oyente no esperaba saber, seguido de la mención natural de tu negocio.
                      </p>
                    )}
                    {mode === 'trivia' && (
                      <p className="mt-1 text-xs text-purple-700 dark:text-purple-300 bg-purple-50 dark:bg-purple-950/30 rounded-lg px-3 py-2">
                        🧠 Pregunta curiosa → el oyente responde por WhatsApp → interacción natural con tu negocio.
                      </p>
                    )}
                    {mode === 'historia' && (
                      <p className="mt-1 text-xs text-blue-700 dark:text-blue-300 bg-blue-50 dark:bg-blue-950/30 rounded-lg px-3 py-2">
                        📖 Mini radionovela de 30s: un personaje con un problema real y tu negocio como la solución creíble.
                      </p>
                    )}
                    {mode === 'alerta' && (
                      <p className="mt-1 text-xs text-red-700 dark:text-red-300 bg-red-50 dark:bg-red-950/30 rounded-lg px-3 py-2">
                        🚨 Información oportuna que el oyente necesita HOY, conectada naturalmente con tu negocio.
                      </p>
                    )}
                    {mode === 'estacional' && (
                      <p className="mt-1 text-xs text-teal-700 dark:text-teal-300 bg-teal-50 dark:bg-teal-950/30 rounded-lg px-3 py-2">
                        🗓️ El mensaje correcto en el momento correcto — conecta tu negocio con lo que la gente ya está viviendo.
                      </p>
                    )}
                  </div>

                  {/* Extra context — trivia (premio), alerta/estacional (fecha/temporada) */}
                  {(mode === 'trivia' || mode === 'alerta' || mode === 'estacional') && (
                    <div>
                      <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">
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
                        className="w-full rounded-lg border border-border px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none" />
                    </div>
                  )}

                  {/* Categoría del negocio (para elegir jingle y contextualizar) */}
                  <div>
                    <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">Categoría del negocio (opcional)</label>
                    <input type="text" placeholder="Ej: farmacia, restaurante, gimnasio, inmobiliaria..."
                      value={businessCategory} onChange={(e) => setBusinessCategory(e.target.value)}
                      className="w-full rounded-lg border border-border px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none" />
                  </div>

                  <div>
                    <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">País / acento del locutor</label>
                    <select value={radioCountry} onChange={(e) => setRadioCountry(e.target.value)}
                      className="w-full rounded-lg border border-border px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none">
                      <option value="mx">🇲🇽 México</option>
                      <option value="co">🇨🇴 Colombia</option>
                      <option value="ar">🇦🇷 Argentina</option>
                      <option value="es">🇪🇸 España</option>
                    </select>
                  </div>
                  {(voicesData?.length ?? 0) > 0 && (
                    <div>
                      <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">Voz del locutor</label>
                      <select value={radioVoiceId} onChange={(e) => setRadioVoiceId(e.target.value)}
                        className="w-full rounded-lg border border-border px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none">
                        <option value="">— Por defecto según país —</option>
                        {voicesData?.map((v) => (
                          <option key={v.id} value={v.id}>{v.name} ({v.gender === 'female' ? 'Femenina' : 'Masculina'})</option>
                        ))}
                      </select>
                    </div>
                  )}
                  {!radioAudioUrl && (
                    <p className="text-xs text-muted-foreground">
                      Claude escribe el guión → voz de locutor → audio .ogg listo para WhatsApp {MODE_BADGE[mode]?.split(' ')[0] || '🎙️'}
                    </p>
                  )}
                  {radioAudioUrl && (
                    <div className="rounded-xl border border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-950/30 p-4 space-y-2">
                      <p className="text-sm font-medium text-green-700 dark:text-green-300">
                        {MODE_BADGE[mode] || '✅'} Cuña generada
                      </p>
                      <audio controls src={radioAudioUrl} className="w-full" />
                      {radioScript && (
                        <details className="text-xs text-muted-foreground">
                          <summary className="cursor-pointer font-medium">Ver guión</summary>
                          <p className="mt-2 whitespace-pre-wrap">{radioScript}</p>
                        </details>
                      )}
                    </div>
                  )}
                </div>
              )}

              {/* ── Voces del Barrio mode ──────────────────────────────────── */}
              {isVocesMode && (
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">
                    📝 Solicitud para tus clientes
                  </label>
                  <textarea rows={2}
                    placeholder='Ej: Mándanos un audio de 10 segundos diciendo cuál es tu platillo favorito 🎙️'
                    value={vocesCollectionPrompt} onChange={(e) => { setVocesCollectionPrompt(e.target.value); setForm({ ...form, message_text: e.target.value }) }}
                    className="w-full rounded-lg border border-border px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none resize-none" />
                  <p className="mt-1 text-xs text-purple-700 dark:text-purple-300 bg-purple-50 dark:bg-purple-950/30 rounded-lg px-3 py-2">
                    🎤 Tus contactos recibirán este mensaje y podrán responder con audios. La IA transcribirá sus historias y después podrás generar una cápsula narrativa con ellas.
                  </p>
                </div>
              )}

              {/* Botón generar */}
              {!isRadioMode && !isVocesMode && (
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
                      className={`w-full rounded-lg border p-3 text-left text-sm transition-all ${form.message_text === v ? 'border-brand-500 bg-brand-50 dark:bg-brand-950/30 text-brand-700 dark:text-brand-300' : 'border-border hover:border-brand-300 hover:bg-muted'}`}>
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
                    <div key={i} className="rounded-lg border border-border bg-muted p-3">
                      <p className="mb-1 text-xs font-medium text-muted-foreground">
                        {mode === 'sequence' ? `Día ${[1, 3, 5][i] ?? i + 1}` : `Semana ${i + 1}`}
                      </p>
                      <textarea rows={3} value={msg}
                        onChange={(e) => {
                          const updated = [...multiMessages]
                          updated[i] = e.target.value
                          setMultiMessages(updated)
                        }}
                        className="w-full rounded border border-border bg-card px-2.5 py-2 text-sm focus:border-brand-500 focus:outline-none resize-none" />
                    </div>
                  ))}
                </div>
              )}

              {/* Mensaje final — solo en regular */}
              {mode === 'regular' && (
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">Mensaje final</label>
                  <textarea rows={3} placeholder="El mensaje que recibirán tus clientes..."
                    value={form.message_text} onChange={(e) => setForm({ ...form, message_text: e.target.value })}
                    className="w-full rounded-lg border border-border px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none resize-none" />
                </div>
              )}

              {/* Cupón */}
              <div className={`rounded-xl border p-4 transition-all ${hasCoupon ? 'border-amber-300 bg-amber-50 dark:bg-amber-950/30' : 'border-border'}`}>
                <label className="flex cursor-pointer items-center gap-2">
                  <input type="checkbox" checked={hasCoupon} onChange={(e) => setHasCoupon(e.target.checked)}
                    className="h-4 w-4 rounded border-border text-amber-500" />
                  <span className="text-sm font-medium text-gray-700">🎫 Incluir cupón con expiración</span>
                </label>
                {hasCoupon && (
                  <div className="mt-3 grid grid-cols-2 gap-3">
                    <div>
                      <label className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">Descripción del cupón</label>
                      <input type="text" placeholder="Ej: 20% de descuento"
                        value={couponDesc} onChange={(e) => setCouponDesc(e.target.value)}
                        className="w-full rounded-lg border border-amber-200 px-3 py-2 text-sm focus:border-amber-400 focus:outline-none" />
                    </div>
                    <div>
                      <label className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">Válido por (horas)</label>
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

              {/* Prueba A/B */}
              <div className={`rounded-xl border p-4 transition-all ${abEnabled ? 'border-purple-300 bg-purple-50 dark:bg-purple-950/30' : 'border-border'}`}>
                <label className="flex cursor-pointer items-center gap-2">
                  <input type="checkbox" checked={abEnabled} onChange={(e) => setAbEnabled(e.target.checked)}
                    className="h-4 w-4 rounded border-border text-purple-500" />
                  <span className="text-sm font-medium text-gray-700">🔬 Prueba A/B</span>
                </label>
                {abEnabled && (
                  <div className="mt-3 space-y-3">
                    {abVariants.map((v, i) => (
                      <div key={i}>
                        <label className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">
                          Variante {String.fromCharCode(65 + i)}
                        </label>
                        <textarea rows={2} placeholder={`Mensaje variante ${String.fromCharCode(65 + i)}...`}
                          value={v} onChange={(e) => {
                            const updated = [...abVariants]
                            updated[i] = e.target.value
                            setAbVariants(updated)
                          }}
                          className="w-full rounded-lg border border-purple-200 dark:border-purple-800 px-3 py-2 text-sm focus:border-purple-400 focus:outline-none resize-none" />
                      </div>
                    ))}
                    {abVariants.length < 3 && (
                      <button onClick={() => setAbVariants([...abVariants, ''])}
                        className="text-xs text-purple-600 hover:text-purple-700 dark:text-purple-300 font-medium">
                        + Añadir variante C
                      </button>
                    )}
                    {abVariants.length === 3 && (
                      <button onClick={() => setAbVariants(abVariants.slice(0, 2))}
                        className="text-xs text-red-500 hover:text-red-600 font-medium">
                        - Quitar variante C
                      </button>
                    )}
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">División</label>
                        <select value={abSplit} onChange={(e) => setAbSplit(e.target.value)}
                          className="w-full rounded-lg border border-purple-200 dark:border-purple-800 px-3 py-2 text-sm focus:border-purple-400 focus:outline-none">
                          <option value="50/50">50% / 50%</option>
                          <option value="70/30">70% / 30%</option>
                          <option value="33/33/34">33% / 33% / 34%</option>
                        </select>
                      </div>
                      <div>
                        <label className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">Métrica</label>
                        <select value={abMetric} onChange={(e) => setAbMetric(e.target.value)}
                          className="w-full rounded-lg border border-purple-200 dark:border-purple-800 px-3 py-2 text-sm focus:border-purple-400 focus:outline-none">
                          <option value="response">Tasa de respuesta</option>
                          <option value="clicks">Tasa de clics</option>
                        </select>
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {/* Programación */}
              <div className="rounded-xl border border-blue-100 dark:border-blue-800 bg-blue-50 dark:bg-blue-950/30 p-4">
                <label className="mb-2 flex items-center gap-2 text-sm font-medium text-blue-800 dark:text-blue-200">
                  <CalendarClock className="h-4 w-4" />
                  Programar envío (opcional)
                </label>
                {optimalTime && (
                  <p className="mb-2 text-xs text-blue-700 dark:text-blue-300 bg-blue-100 dark:bg-blue-900/50 rounded-lg px-3 py-2">
                    💡 Tus contactos responden más entre las <strong>{optimalTime.best_window}</strong> — considera enviarlo en ese horario.
                  </p>
                )}
                <input
                  type="datetime-local"
                  value={scheduledAt}
                  min={new Date().toISOString().slice(0, 16)}
                  onChange={(e) => setScheduledAt(e.target.value)}
                  className="w-full rounded-lg border border-blue-200 dark:border-blue-800 bg-card px-3 py-2 text-sm focus:border-blue-400 focus:outline-none"
                />
                {scheduledAt && (
                  <p className="mt-1.5 text-xs text-blue-600 dark:text-blue-300">
                    La campaña se enviará el {new Date(scheduledAt).toLocaleString('es-MX', { dateStyle: 'long', timeStyle: 'short' })}
                  </p>
                )}
              </div>

              {error && <p className="text-sm text-red-600">{error}</p>}
            </div>

            <div className="mt-5 flex gap-3">
              <button onClick={() => { setShowCreate(false); resetForm() }}
                className="flex-1 rounded-lg border border-border py-2.5 text-sm text-gray-700 hover:bg-muted">
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
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 dark:bg-black/80 p-4" onClick={() => setShowParrilla(false)}>
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
              <button onClick={() => setShowParrilla(false)} className="text-muted-foreground hover:text-gray-600 dark:hover:text-gray-400">
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Formulario Izquierdo */}
              <div className="col-span-1 space-y-4 border-r pr-6">
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">Nombre del negocio</label>
                  <input type="text" placeholder="Ej: Pizzería Don Corleone"
                    value={parrillaBusinessName} onChange={(e) => setParrillaBusinessName(e.target.value)}
                    className="w-full rounded-lg border border-border px-3 py-2 text-sm focus:border-brand-500 focus:outline-none" />
                </div>
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">Propósito principal de la semana</label>
                  <textarea rows={3} placeholder="Ej: Anunciar nuestras nuevas pizzas veganas y la promo del 2x1 los jueves"
                    value={parrillaIntent} onChange={(e) => setParrillaIntent(e.target.value)}
                    className="w-full rounded-lg border border-border px-3 py-2 text-sm focus:border-brand-500 focus:outline-none resize-none" />
                </div>
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">Categoría (opcional)</label>
                  <input type="text" placeholder="Ej: restaurante, zapatería"
                    value={parrillaCategory} onChange={(e) => setParrillaCategory(e.target.value)}
                    className="w-full rounded-lg border border-border px-3 py-2 text-sm focus:border-brand-500 focus:outline-none" />
                </div>
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">Contexto extra (opcional)</label>
                  <input type="text" placeholder="Ej: Premio de la trivia, temporada"
                    value={parrillaContext} onChange={(e) => setParrillaContext(e.target.value)}
                    className="w-full rounded-lg border border-border px-3 py-2 text-sm focus:border-brand-500 focus:outline-none" />
                </div>
                <div className="rounded-xl border border-blue-100 dark:border-blue-800 bg-blue-50 dark:bg-blue-950/30 p-4 space-y-3">
                  <label className="flex cursor-pointer items-start gap-2">
                    <input type="checkbox" checked={parrillaAutoSchedule} onChange={(e) => setParrillaAutoSchedule(e.target.checked)}
                      className="mt-0.5 h-4 w-4 rounded border-border text-blue-600 dark:text-blue-300 focus:ring-blue-500" />
                    <div>
                      <span className="text-sm font-medium text-blue-900 dark:text-blue-100">Programar envíos automáticos</span>
                      <p className="text-xs text-blue-700 dark:text-blue-300">Si está activo, se enviará cada día automáticamente a la hora elegida.</p>
                    </div>
                  </label>
                  {parrillaAutoSchedule && (
                    <div>
                      <label className="mb-1 block text-xs font-medium text-blue-800 dark:text-blue-200">Hora de envío local</label>
                      <input type="time" value={parrillaSendTime} onChange={(e) => setParrillaSendTime(e.target.value)}
                        className="w-full rounded border border-blue-200 dark:border-blue-800 px-2 py-1.5 text-sm" />
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
                  <div className="flex h-full flex-col items-center justify-center rounded-xl border border-dashed border-border bg-muted py-12 text-center">
                    <CalendarRange className="h-12 w-12 text-gray-300 mb-3" />
                    <p className="text-sm font-medium text-muted-foreground">Llena los datos y haz clic en Generar</p>
                    <p className="mt-1 text-xs text-muted-foreground">Crearemos 7 cuñas distintas optimizadas para cada día.</p>
                  </div>
                )}
                {parrillaGenerating && (
                  <div className="flex h-full flex-col items-center justify-center rounded-xl bg-muted py-12 text-center">
                    <div className="h-8 w-8 animate-spin rounded-full border-4 border-brand-200 border-t-brand-500 mb-4" />
                    <p className="text-sm font-medium text-gray-700">Escribiendo y grabando 7 cuñas...</p>
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
                            <span className="font-semibold text-gray-800">{d.day_name}</span>
                            <span className="text-xs font-medium text-muted-foreground flex items-center gap-1 bg-muted px-2 py-0.5 rounded-full">
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
                          <div className="text-xs text-gray-600 dark:text-gray-400 bg-muted p-2 rounded border border-border flex-1 overflow-y-auto max-h-24 print-no-overflow">
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
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 dark:bg-black/80 p-4" onClick={() => setAnalyticsId(null)}>
          <div className="w-full max-w-md rounded-2xl bg-card p-6 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="mb-5 flex items-center justify-between">
              <div>
                <h3 className="font-semibold text-foreground">{analyticsTarget.name}</h3>
                <span className={`mt-1 inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_COLORS[analyticsTarget.status] ?? 'bg-muted text-gray-600 dark:bg-gray-800 dark:text-gray-400'}`}>
                  {STATUS_LABELS[analyticsTarget.status] ?? analyticsTarget.status}
                </span>
              </div>
              <button onClick={() => setAnalyticsId(null)} className="text-muted-foreground hover:text-gray-600 dark:hover:text-gray-400">
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* Recharts bar chart */}
            {(() => {
              const s = analyticsTarget.stats
              const sent = s.sent ?? 0
              const chartData = [
                { name: 'Enviados', value: sent, fill: '#60a5fa' },
                { name: 'Entregados', value: s.delivered ?? 0, fill: '#34d399' },
                { name: 'Leídos', value: s.read ?? 0, fill: '#818cf8' },
                { name: 'Respondidos', value: s.replied ?? 0, fill: '#f59e0b' },
                { name: 'Fallidos', value: s.failed ?? 0, fill: '#f87171' },
                { name: 'Cupones', value: s.coupons_redeemed ?? 0, fill: '#fb923c' },
              ]
              return (
                <div className="space-y-4">
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={chartData} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
                      <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                      <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                      <Tooltip formatter={(v: number) => [v.toLocaleString(), '']} labelStyle={{ fontWeight: 600 }} />
                      <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                        {chartData.map((entry, i) => <Cell key={i} fill={entry.fill} />)}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                  {sent > 0 && (
                    <div className="grid grid-cols-2 gap-2 text-sm">
                      <div className="rounded-lg bg-green-50 dark:bg-green-950/30 p-2 text-center">
                        <div className="font-semibold text-green-700 dark:text-green-300">{Math.round(((s.delivered ?? 0) / sent) * 100)}%</div>
                        <div className="text-xs text-green-600">Entrega</div>
                      </div>
                      <div className="rounded-lg bg-brand-50 dark:bg-brand-950/30 p-2 text-center">
                        <div className="font-semibold text-brand-700 dark:text-brand-300">{Math.round(((s.replied ?? 0) / sent) * 100)}%</div>
                        <div className="text-xs text-brand-600 dark:text-brand-400">Respuesta</div>
                      </div>
                    </div>
                  )}
                </div>
              )
            })()}

            {analyticsTarget.schedule?.start_date && (
              <p className="mt-4 text-xs text-muted-foreground">
                Programada para {new Date(analyticsTarget.schedule.start_date).toLocaleString('es-MX', { dateStyle: 'long', timeStyle: 'short' })}
              </p>
            )}
          </div>
        </div>
      )}

      {/* Voces del Barrio Detail Modal */}
      {vocesDetailTarget && (() => {
        const generateCapsule = async () => {
          setCapsuleGenerating(true)
          try {
            const { data } = await api.post(`/campaigns/${vocesDetailTarget.id}/generate-capsule`)
            setCapsuleAudioUrl(data.audio_url)
            setCapsuleScript(data.script ?? '')
          } catch (err: unknown) {
            setError(getApiError(err, 'Error al generar cápsula'))
          } finally {
            setCapsuleGenerating(false)
          }
        }

        return (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 dark:bg-black/80 p-4" onClick={() => setVocesDetailId(null)}>
            <div className="w-full max-w-lg rounded-2xl bg-card p-6 shadow-2xl max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
              <div className="mb-5 flex items-center justify-between">
                <div>
                  <h3 className="font-semibold text-foreground">🎤 {vocesDetailTarget.name}</h3>
                  <p className="mt-0.5 text-xs text-muted-foreground">Voces del Barrio — Historias de clientes</p>
                </div>
                <button onClick={() => setVocesDetailId(null)} className="text-muted-foreground hover:text-gray-600 dark:hover:text-gray-400">
                  <X className="h-5 w-5" />
                </button>
              </div>

              {storiesLoading ? (
                <div className="flex items-center justify-center py-8">
                  <span className="h-6 w-6 animate-spin rounded-full border-2 border-purple-500 border-t-transparent" />
                </div>
              ) : storiesData && storiesData.stories.length > 0 ? (
                <>
                  <div className="mb-3 flex items-center gap-3 text-sm text-muted-foreground">
                    <span>📥 Total: {storiesData.total}</span>
                    <span className="text-green-600 dark:text-green-300">✅ Aprobadas: {storiesData.approved_count}</span>
                    <span className="text-yellow-600 dark:text-yellow-300">⏳ Pendientes: {storiesData.pending_count}</span>
                  </div>

                  <div className="space-y-3 mb-4 max-h-80 overflow-y-auto">
                    {storiesData.stories.map((story: { id: string; contact_name?: string; sentiment: string; transcription: string; approved: boolean; created_at: string }) => (
                      <div key={story.id} className="flex items-start gap-3 rounded-xl border border-border bg-card p-3">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <p className="text-sm font-medium text-foreground">{story.contact_name || 'Cliente'}</p>
                            <span className={`text-xs px-1.5 py-0.5 rounded-full ${
                              story.sentiment === 'positivo' ? 'bg-green-100 text-green-600 dark:bg-green-900/50 dark:text-green-300' :
                              story.sentiment === 'negativo' ? 'bg-red-100 text-red-600 dark:bg-red-900/50 dark:text-red-300' :
                              'bg-muted text-muted-foreground'
                            }`}>{story.sentiment}</span>
                          </div>
                          <p className="mt-0.5 text-xs text-muted-foreground line-clamp-3">{story.transcription}</p>
                          <p className="mt-1 text-[10px] text-muted-foreground">
                            {new Date(story.created_at).toLocaleString('es-MX', { dateStyle: 'short', timeStyle: 'short' })}
                          </p>
                        </div>
                        <button
                          onClick={() => approveStoryMutation.mutate(story.id)}
                          className={`shrink-0 rounded-lg px-2.5 py-1 text-xs font-medium transition-colors ${
                            story.approved
                              ? 'bg-green-100 text-green-700 dark:text-green-300 hover:bg-green-200'
                              : 'bg-yellow-100 text-yellow-700 dark:text-yellow-300 hover:bg-yellow-200'
                          }`}>
                          {story.approved ? '✅ Aprobada' : '⏳ Aprobar'}
                        </button>
                      </div>
                    ))}
                  </div>

                  <div className="border-t border-border pt-4 space-y-3">
                    <button onClick={generateCapsule} disabled={capsuleGenerating || storiesData.approved_count === 0}
                      className="flex w-full items-center justify-center gap-2 rounded-lg bg-purple-500 px-4 py-2.5 text-sm font-medium text-white hover:bg-purple-600 disabled:opacity-60 transition-colors">
                      <Sparkles className="h-4 w-4" />
                      {capsuleGenerating ? 'Generando cápsula...' : capsuleAudioUrl ? '🎤 Regenerar cápsula narrativa' : '🎤 Generar cápsula narrativa'}
                    </button>
                    {storiesData.approved_count === 0 && (
                      <p className="text-center text-xs text-yellow-600 dark:text-yellow-300">Aprueba al menos una historia para generar la cápsula</p>
                    )}

                    {capsuleAudioUrl && (
                      <div className="rounded-xl border border-purple-200 dark:border-purple-800 bg-purple-50 dark:bg-purple-950/30 p-4 space-y-2">
                        <p className="text-sm font-medium text-purple-700 dark:text-purple-300">🎤 Cápsula generada</p>
                        <audio controls src={capsuleAudioUrl} className="w-full" />
                        {capsuleScript && (
                          <details className="text-xs text-muted-foreground">
                            <summary className="cursor-pointer font-medium">Ver guión</summary>
                            <p className="mt-2 whitespace-pre-wrap">{capsuleScript}</p>
                          </details>
                        )}
                      </div>
                    )}
                  </div>
                </>
              ) : (
                <div className="text-center py-8 text-muted-foreground">
                  <Megaphone className="mx-auto h-10 w-10 mb-2" />
                  <p className="text-sm font-medium">No hay historias todavía</p>
                  <p className="text-xs mt-1">Cuando tus contactos envíen audios a esta campaña, aparecerán aquí</p>
                </div>
              )}
            </div>
          </div>
        )
      })()}
    </div>
    </div>
    </>
  )
}
