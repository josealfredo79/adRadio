import { useEffect, useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Copy, CheckCheck, ExternalLink, Smartphone, Palette, MessageSquare, MoveHorizontal, Save, Sparkles, Globe, ArrowRight, ArrowLeft, ArrowUp, ArrowDown, Pencil, Image as ImageIcon } from 'lucide-react'
import api, { getApiError } from '@/lib/api'
import SEO from '@/components/SEO'
import { useAuth } from '@/contexts/AuthContext'
import { SITE_THEMES } from '@/pages/publicSite/theme'
import {
  DAY_ORDER,
  DEFAULT_BUSINESS_HOURS,
  DEFAULT_LANDING_SECTIONS,
  LANDING_SECTION_IDS,
  LANDING_SECTION_LABELS,
  type BusinessHours,
  type LandingSectionId,
} from '@/pages/publicSite/utils'
import BusinessHoursEditor from '@/components/BusinessHoursEditor'

const SITE_URL = (import.meta.env.VITE_SITE_URL as string | undefined) ?? (typeof window !== 'undefined' ? window.location.origin : '')

function slugify(text: string): string {
  return text
    .toLowerCase()
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '') // strip accents
    .replace(/[^a-z0-9\s-]/g, '')
    .trim()
    .replace(/\s+/g, '-')
    .slice(0, 50)
}

const SLUG_RE = /^[a-z0-9](?:[a-z0-9-]{1,48}[a-z0-9])?$/

const PRESET_COLORS = [
  '#25D366', '#674CC4', '#3B82F6', '#EC4899', '#F59E0B', '#EF4444',
]

function ColorPickerRow({ value, onChange }: { value: string; onChange: (hex: string) => void }) {
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        {PRESET_COLORS.map((c) => (
          <button
            key={c}
            type="button"
            onClick={() => onChange(c)}
            className={`w-9 h-9 rounded-full border-2 transition-all ${value === c ? 'border-gray-800 dark:border-gray-200 scale-110' : 'border-transparent'}`}
            style={{ background: c }}
          />
        ))}
      </div>
      <div className="flex items-center gap-2">
        <span className="text-xs text-gray-400 dark:text-gray-500">o hex:</span>
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-24 rounded-lg border border-gray-300 dark:border-gray-700 px-2 py-1.5 text-xs font-mono bg-background text-foreground focus:border-brand-500 dark:focus:border-brand-400 focus:outline-none"
          maxLength={7}
        />
      </div>
    </div>
  )
}

interface SectionRow {
  id: LandingSectionId
  visible: boolean
}

function seedSectionOrder(saved: LandingSectionId[] | null | undefined): SectionRow[] {
  if (!saved?.length) return DEFAULT_LANDING_SECTIONS.map((id) => ({ id, visible: true }))
  const visibleSet = new Set(saved)
  const ordered = [...saved, ...LANDING_SECTION_IDS.filter((id) => !saved.includes(id))]
  return ordered.map((id) => ({ id, visible: visibleSet.has(id) }))
}

function LandingPageWizard({ config, openSignal }: { config?: { color: string; greeting: string; position: 'left' | 'right' }; openSignal?: number }) {
  const { user, setUser } = useAuth()
  const qc = useQueryClient()
  const published = !!user?.slug

  const [editing, setEditing] = useState(false)
  const [step, setStep] = useState<1 | 2 | 3>(1)
  const [slug, setSlug] = useState(user?.slug ?? slugify(user?.business_name ?? ''))
  const [tagline, setTagline] = useState(user?.landing_tagline ?? '')
  const [siteTheme, setSiteTheme] = useState(user?.site_theme ?? 'medianoche')
  const [accentColor, setAccentColor] = useState(user?.widget_color ?? '#25D366')
  const [sectionOrder, setSectionOrder] = useState<SectionRow[]>(() => seedSectionOrder(user?.landing_sections as LandingSectionId[] | undefined))
  const [businessHours, setBusinessHours] = useState<BusinessHours>(user?.business_hours ?? DEFAULT_BUSINESS_HOURS)
  const [copied, setCopied] = useState(false)
  const [aiHint, setAiHint] = useState('')
  const [aiSuggestions, setAiSuggestions] = useState<string[] | null>(null)
  const logoInputRef = useRef<HTMLInputElement>(null)
  const [uploadingLogo, setUploadingLogo] = useState(false)
  const [logoError, setLogoError] = useState('')
  const heroInputRef = useRef<HTMLInputElement>(null)
  const [uploadingHero, setUploadingHero] = useState(false)
  const [heroError, setHeroError] = useState('')

  const slugValid = SLUG_RE.test(slug)
  const hoursValid = DAY_ORDER.every((day) => {
    const v = businessHours[day]
    return !v || v[0] < v[1]
  })

  const moveSection = (index: number, dir: -1 | 1) => {
    setSectionOrder((prev) => {
      const next = [...prev]
      const target = index + dir
      if (target < 0 || target >= next.length) return prev
      ;[next[index], next[target]] = [next[target], next[index]]
      return next
    })
  }

  const toggleSectionVisible = (index: number) => {
    setSectionOrder((prev) => prev.map((s, i) => (i === index ? { ...s, visible: !s.visible } : s)))
  }

  const suggestMutation = useMutation({
    mutationFn: () => api.post('/me/landing-tagline/suggest', { hint: aiHint }, { timeout: 30000 }).then((r) => r.data as { suggestions: string[] }),
    onSuccess: (data) => setAiSuggestions(data.suggestions),
  })

  const publishMutation = useMutation({
    mutationFn: async () => {
      const [profileRes] = await Promise.all([
        api.patch('/me', {
          slug,
          landing_tagline: tagline,
          site_theme: siteTheme,
          landing_sections: sectionOrder.filter((s) => s.visible).map((s) => s.id),
          business_hours: businessHours,
        }),
        api.put('/widget/config', {
          color: accentColor,
          greeting: config?.greeting ?? '¡Hola! ¿En qué puedo ayudarte?',
          position: config?.position ?? 'right',
        }),
      ])
      return profileRes.data
    },
    onSuccess: (updated) => {
      if (setUser) setUser(updated)
      qc.invalidateQueries({ queryKey: ['widget-config'] })
      setEditing(false)
      setStep(1)
    },
  })

  const handleLogoUpload = async (file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    setUploadingLogo(true)
    setLogoError('')
    try {
      const r = await api.post('/me/logo', fd)
      if (setUser) setUser(r.data)
    } catch (err: unknown) {
      setLogoError(getApiError(err, 'No se pudo subir el logo'))
    } finally {
      setUploadingLogo(false)
      if (logoInputRef.current) logoInputRef.current.value = ''
    }
  }

  const handleHeroUpload = async (file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    setUploadingHero(true)
    setHeroError('')
    try {
      const r = await api.post('/me/hero-image', fd)
      if (setUser) setUser(r.data)
    } catch (err: unknown) {
      setHeroError(getApiError(err, 'No se pudo subir la foto de portada'))
    } finally {
      setUploadingHero(false)
      if (heroInputRef.current) heroInputRef.current.value = ''
    }
  }

  const startEditing = (openToStep: 1 | 2 | 3 = 1) => {
    setSlug(user?.slug ?? slugify(user?.business_name ?? ''))
    setTagline(user?.landing_tagline ?? '')
    setSiteTheme(user?.site_theme ?? 'medianoche')
    setAccentColor(user?.widget_color ?? '#25D366')
    setSectionOrder(seedSectionOrder(user?.landing_sections as LandingSectionId[] | undefined))
    setBusinessHours(user?.business_hours ?? DEFAULT_BUSINESS_HOURS)
    setAiHint('')
    setAiSuggestions(null)
    setLogoError('')
    setHeroError('')
    setStep(openToStep)
    publishMutation.reset()
    suggestMutation.reset()
    setEditing(true)
  }

  useEffect(() => {
    if (openSignal) startEditing(3)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openSignal])

  const siteLink = `${SITE_URL}/sitio/${user?.slug}`

  const handleCopyLink = () => {
    navigator.clipboard.writeText(siteLink)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  if (published && !editing) {
    return (
      <div className="bg-white dark:bg-gray-950 border border-gray-200 dark:border-gray-800 rounded-xl p-5 space-y-3">
        <div className="flex items-center gap-2 text-sm font-semibold text-gray-700 dark:text-gray-300">
          <Globe size={16} />
          Tu página web
        </div>
        <p className="text-sm text-gray-500 dark:text-gray-400">Tu página ya está publicada y lista para compartir.</p>
        <div className="flex items-center gap-2 flex-wrap">
          <a
            href={siteLink}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm text-brand-600 dark:text-brand-400 hover:underline font-mono break-all"
          >
            {siteLink}
          </a>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleCopyLink}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 bg-gray-100 dark:bg-gray-900 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-800 transition"
          >
            {copied ? <CheckCheck size={14} /> : <Copy size={14} />}
            {copied ? 'Copiado!' : 'Copiar link'}
          </button>
          <button
            onClick={() => startEditing()}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 bg-gray-100 dark:bg-gray-900 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-800 transition"
          >
            <Pencil size={14} />
            Editar
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="bg-white dark:bg-gray-950 border border-gray-200 dark:border-gray-800 rounded-xl p-5 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm font-semibold text-gray-700 dark:text-gray-300">
          <Globe size={16} />
          {published ? 'Editar tu página' : 'Crea tu página web'}
        </div>
        <span className="text-xs text-gray-400 dark:text-gray-500">Paso {step} de 3</span>
      </div>

      {!published && step === 1 && (
        <p className="text-sm text-gray-500 dark:text-gray-400">
          AdRadio te da una página pública con tu bot integrado — funciona aunque tu WhatsApp esté desconectado o en revisión.
        </p>
      )}

      {step === 1 && (
        <div className="space-y-2">
          <label className="text-xs font-medium text-gray-600 dark:text-gray-400">Elige el link de tu página</label>
          <div className="flex items-center rounded-lg border border-gray-300 dark:border-gray-700 overflow-hidden focus-within:border-brand-500 dark:focus-within:border-brand-400">
            <span className="px-3 py-2 text-xs text-gray-400 dark:text-gray-500 bg-gray-50 dark:bg-gray-900 border-r border-gray-200 dark:border-gray-800 shrink-0">
              {SITE_URL.replace(/^https?:\/\//, '')}/sitio/
            </span>
            <input
              type="text"
              value={slug}
              onChange={(e) => setSlug(slugify(e.target.value))}
              className="flex-1 min-w-0 px-3 py-2 text-sm bg-transparent text-gray-900 dark:text-gray-100 focus:outline-none"
              placeholder="mi-negocio"
              maxLength={50}
            />
          </div>
          {slug && !slugValid && (
            <p className="text-xs text-red-500">Solo letras minúsculas, números y guiones (2-50 caracteres).</p>
          )}
          <button
            onClick={() => setStep(2)}
            disabled={!slugValid}
            className="w-full flex items-center justify-center gap-2 rounded-lg bg-brand-500 dark:bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600 dark:hover:bg-brand-500 disabled:opacity-50 transition-colors"
          >
            Siguiente
            <ArrowRight size={14} />
          </button>
        </div>
      )}

      {step === 2 && (
        <div className="space-y-3">
          {/* Logo */}
          <div className="space-y-2">
            <label className="text-xs font-medium text-gray-600 dark:text-gray-400">Logo de tu negocio (opcional)</label>
            <div className="flex items-center gap-3">
              {user?.logo_url ? (
                <img src={user.logo_url} alt="Logo" className="h-12 w-12 rounded-lg object-cover border border-gray-200 dark:border-gray-800" />
              ) : (
                <div className="h-12 w-12 rounded-lg border border-dashed border-gray-300 dark:border-gray-700 flex items-center justify-center text-gray-300 dark:text-gray-600">
                  <ImageIcon size={18} />
                </div>
              )}
              <button
                type="button"
                onClick={() => logoInputRef.current?.click()}
                disabled={uploadingLogo}
                className="flex items-center justify-center gap-1.5 rounded-lg bg-gray-100 dark:bg-gray-900 px-3 py-1.5 text-xs font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-800 disabled:opacity-50 transition-colors"
              >
                {uploadingLogo ? 'Subiendo...' : user?.logo_url ? 'Cambiar logo' : 'Subir logo'}
              </button>
              <input
                ref={logoInputRef}
                type="file"
                accept="image/jpeg,image/png,image/webp"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0]
                  if (file) handleLogoUpload(file)
                }}
              />
            </div>
            {logoError && <p className="text-xs text-red-500">{logoError}</p>}
          </div>

          {/* Foto de portada */}
          <div className="space-y-2">
            <label className="text-xs font-medium text-gray-600 dark:text-gray-400">Foto de portada (opcional)</label>
            <div className="flex items-center gap-3">
              {user?.hero_image_url ? (
                <img src={user.hero_image_url} alt="Portada" className="h-12 w-20 rounded-lg object-cover border border-gray-200 dark:border-gray-800" />
              ) : (
                <div className="h-12 w-20 rounded-lg border border-dashed border-gray-300 dark:border-gray-700 flex items-center justify-center text-gray-300 dark:text-gray-600">
                  <ImageIcon size={18} />
                </div>
              )}
              <button
                type="button"
                onClick={() => heroInputRef.current?.click()}
                disabled={uploadingHero}
                className="flex items-center justify-center gap-1.5 rounded-lg bg-gray-100 dark:bg-gray-900 px-3 py-1.5 text-xs font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-800 disabled:opacity-50 transition-colors"
              >
                {uploadingHero ? 'Subiendo...' : user?.hero_image_url ? 'Cambiar foto' : 'Subir foto'}
              </button>
              <input
                ref={heroInputRef}
                type="file"
                accept="image/jpeg,image/png,image/webp"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0]
                  if (file) handleHeroUpload(file)
                }}
              />
            </div>
            {heroError && <p className="text-xs text-red-500">{heroError}</p>}
          </div>

          {/* Tema de color */}
          <div className="space-y-2">
            <label className="text-xs font-medium text-gray-600 dark:text-gray-400">Estilo de tu página</label>
            <div className="flex flex-wrap gap-2">
              {Object.entries(SITE_THEMES).map(([key, t]) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setSiteTheme(key)}
                  title={t.name}
                  className={`w-12 h-9 rounded-lg overflow-hidden border-2 transition-all ${siteTheme === key ? 'border-brand-500 scale-105' : 'border-transparent'}`}
                  style={{ background: t.bg }}
                >
                  <span className="block w-4 h-4 m-1 rounded" style={{ background: t.cardBg, border: `1px solid ${t.cardBorder}` }} />
                </button>
              ))}
            </div>
          </div>

          <div className="space-y-2">
            <label className="text-xs font-medium text-gray-600 dark:text-gray-400">Una frase corta para tus visitantes (opcional)</label>
            <textarea
              value={tagline}
              onChange={(e) => setTagline(e.target.value)}
              maxLength={140}
              rows={2}
              placeholder="Ej. El mejor sabor de la ciudad, a un mensaje de distancia"
              className="w-full rounded-lg border border-gray-300 dark:border-gray-700 px-3 py-2 text-sm bg-transparent text-gray-900 dark:text-gray-100 focus:border-brand-500 dark:focus:border-brand-400 focus:outline-none resize-none"
            />
            <p className="text-xs text-gray-400 dark:text-gray-500 text-right">{tagline.length}/140</p>
          </div>

          {/* Generar con IA */}
          <div className="rounded-lg border border-dashed border-gray-300 dark:border-gray-700 p-3 space-y-2">
            <div className="flex items-center gap-1.5 text-xs font-medium text-gray-600 dark:text-gray-400">
              <Sparkles size={13} />
              ¿No sabes qué escribir? Deja que la IA te sugiera
            </div>
            <input
              type="text"
              value={aiHint}
              onChange={(e) => setAiHint(e.target.value)}
              placeholder="Cuéntame algo de tu negocio (opcional)"
              maxLength={300}
              className="w-full rounded-lg border border-gray-300 dark:border-gray-700 px-3 py-1.5 text-xs bg-transparent text-gray-900 dark:text-gray-100 focus:border-brand-500 dark:focus:border-brand-400 focus:outline-none"
            />
            <button
              type="button"
              onClick={() => suggestMutation.mutate()}
              disabled={suggestMutation.isPending}
              className="flex items-center justify-center gap-1.5 rounded-lg bg-gray-100 dark:bg-gray-900 px-3 py-1.5 text-xs font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-800 disabled:opacity-50 transition-colors"
            >
              <Sparkles size={13} />
              {suggestMutation.isPending ? 'Generando...' : 'Generar con IA'}
            </button>
            {suggestMutation.isError && (
              <p className="text-xs text-red-500">{getApiError(suggestMutation.error, 'No se pudo generar, intenta de nuevo')}</p>
            )}
            {aiSuggestions && (
              <div className="space-y-1.5 pt-1">
                {aiSuggestions.map((s, i) => (
                  <button
                    key={i}
                    type="button"
                    onClick={() => setTagline(s)}
                    className="w-full text-left text-xs px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-800 hover:border-brand-500 dark:hover:border-brand-400 hover:bg-brand-50 dark:hover:bg-brand-950/30 text-gray-700 dark:text-gray-300 transition-colors"
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Mini preview */}
          <div className="rounded-lg border border-gray-200 dark:border-gray-800 p-4 text-center bg-gray-50 dark:bg-gray-900">
            <div className="text-3xl mb-1">🎙️</div>
            <p className="font-bold text-sm text-gray-900 dark:text-gray-100">{user?.business_name || 'Tu negocio'}</p>
            {tagline && <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">{tagline}</p>}
          </div>

          <div className="flex gap-2">
            <button
              onClick={() => setStep(1)}
              className="flex items-center justify-center gap-1.5 rounded-lg border border-gray-300 dark:border-gray-700 px-4 py-2 text-sm font-medium text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-900 transition-colors"
            >
              <ArrowLeft size={14} />
              Atrás
            </button>
            <button
              onClick={() => setStep(3)}
              className="flex-1 flex items-center justify-center gap-2 rounded-lg bg-brand-500 dark:bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600 dark:hover:bg-brand-500 transition-colors"
            >
              Siguiente
              <ArrowRight size={14} />
            </button>
          </div>
        </div>
      )}

      {step === 3 && (
        <div className="space-y-4">
          {/* Secciones de la página */}
          <div className="space-y-2">
            <label className="text-xs font-medium text-gray-600 dark:text-gray-400">Secciones de tu página (ordena y muestra/oculta)</label>
            <div className="space-y-1.5">
              {sectionOrder.map((s, i) => (
                <div
                  key={s.id}
                  className="flex items-center gap-2 rounded-lg border border-gray-200 dark:border-gray-800 px-3 py-2"
                >
                  <input
                    type="checkbox"
                    checked={s.visible}
                    onChange={() => toggleSectionVisible(i)}
                    className="shrink-0"
                  />
                  <span className="flex-1 text-sm text-gray-700 dark:text-gray-300">{LANDING_SECTION_LABELS[s.id]}</span>
                  <button
                    type="button"
                    onClick={() => moveSection(i, -1)}
                    disabled={i === 0}
                    aria-label="Subir sección"
                    className="p-1 rounded text-gray-400 dark:text-gray-500 hover:text-gray-700 dark:hover:text-gray-200 disabled:opacity-30"
                  >
                    <ArrowUp size={14} />
                  </button>
                  <button
                    type="button"
                    onClick={() => moveSection(i, 1)}
                    disabled={i === sectionOrder.length - 1}
                    aria-label="Bajar sección"
                    className="p-1 rounded text-gray-400 dark:text-gray-500 hover:text-gray-700 dark:hover:text-gray-200 disabled:opacity-30"
                  >
                    <ArrowDown size={14} />
                  </button>
                </div>
              ))}
            </div>
          </div>

          {/* Horario de atención — también controla qué horarios de cita
              ofrece el bot (ver BusinessHoursEditor.tsx); ese mismo editor
              está duplicado en AppointmentsPage.tsx para que sea
              descubrible desde ahí también. */}
          <div className="space-y-2">
            <label className="text-xs font-medium text-gray-600 dark:text-gray-400">Horario de atención</label>
            <BusinessHoursEditor value={businessHours} onChange={setBusinessHours} />
          </div>

          {/* Color de acento */}
          <div className="space-y-2">
            <label className="text-xs font-medium text-gray-600 dark:text-gray-400">Color de acento de tu página</label>
            <ColorPickerRow value={accentColor} onChange={setAccentColor} />
          </div>

          {publishMutation.isError && (
            <p className="text-xs text-red-500">{getApiError(publishMutation.error, 'No se pudo publicar')}</p>
          )}

          <div className="flex gap-2">
            <button
              onClick={() => setStep(2)}
              className="flex items-center justify-center gap-1.5 rounded-lg border border-gray-300 dark:border-gray-700 px-4 py-2 text-sm font-medium text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-900 transition-colors"
            >
              <ArrowLeft size={14} />
              Atrás
            </button>
            <button
              onClick={() => publishMutation.mutate()}
              disabled={publishMutation.isPending || !hoursValid}
              className="flex-1 flex items-center justify-center gap-2 rounded-lg bg-brand-500 dark:bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600 dark:hover:bg-brand-500 disabled:opacity-50 transition-colors"
            >
              <Save size={14} />
              {publishMutation.isPending ? 'Publicando...' : published ? 'Guardar cambios' : 'Publicar'}
            </button>
          </div>
          {published && (
            <button
              onClick={() => { setEditing(false); setStep(1) }}
              className="w-full text-xs text-gray-400 dark:text-gray-500 hover:underline"
            >
              Cancelar
            </button>
          )}
        </div>
      )}
    </div>
  )
}

interface SnippetData {
  snippet: string
}

interface WidgetConfig {
  color: string
  greeting: string
  position: 'left' | 'right'
}

export default function WidgetPage() {
  const { user } = useAuth()
  const qc = useQueryClient()
  const [copied, setCopied] = useState(false)
  const [openWizardSignal, setOpenWizardSignal] = useState(0)

  const { data: snippet, isLoading } = useQuery<SnippetData>({
    queryKey: ['widget-snippet'],
    queryFn: () => api.get('/widget/snippet').then(r => r.data),
    staleTime: 60_000,
  })

  const { data: config } = useQuery<WidgetConfig>({
    queryKey: ['widget-config'],
    queryFn: () => api.get('/widget/config').then(r => r.data),
    staleTime: 60_000,
  })

  const [form, setForm] = useState<WidgetConfig | null>(null)

  const configData = form ?? config ?? { color: '#25D366', greeting: '¡Hola! ¿En qué puedo ayudarte?', position: 'right' }

  const saveMutation = useMutation({
    mutationFn: (data: WidgetConfig) => api.put('/widget/config', data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['widget-config'] })
      qc.invalidateQueries({ queryKey: ['widget-snippet'] })
    },
  })

  const handleCopy = () => {
    if (!snippet?.snippet) return
    navigator.clipboard.writeText(snippet.snippet)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <>
      <SEO title="Widget" description="Panel de control de IaRadio." noIndex />
      <div className="max-w-4xl mx-auto p-6 space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Widget de chat</h1>
        <p className="mt-1 text-gray-500 dark:text-gray-400 text-sm">
          Agrega un botón flotante a tu sitio web. Tus visitantes chatean directo ahí con tu bot (usando tu base de conocimiento) sin salir de tu página — no depende de tener WhatsApp conectado. Personaliza colores, saludo y posición.
        </p>
      </div>

      {!user?.whatsapp_number && (
        <div className="flex items-start gap-3 rounded-xl border border-emerald-200 dark:border-emerald-800 bg-emerald-50 dark:bg-emerald-950/30 px-5 py-4">
          <Sparkles className="h-5 w-5 shrink-0 text-emerald-600 dark:text-emerald-400 mt-0.5" />
          <div>
            <p className="text-sm font-semibold text-emerald-800 dark:text-emerald-200">
              Aún no conectas WhatsApp — no hay problema, ya puedes operar con el widget
            </p>
            <p className="mt-1 text-sm text-emerald-700 dark:text-emerald-300">
              Tu bot puede empezar a atender a los visitantes de tu sitio hoy mismo, sin esperar a conectar tu número. Cuando conectes WhatsApp, tendrás ambos canales funcionando juntos.
            </p>
          </div>
        </div>
      )}

      <LandingPageWizard config={config} openSignal={openWizardSignal} />

      {/* Customization */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Preview */}
        <div className="bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-6 relative overflow-hidden order-2 lg:order-1">
          <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400 mb-4">
            <Smartphone size={16} />
            Vista previa en vivo
          </div>
          <div className="bg-white dark:bg-gray-950 border border-gray-200 dark:border-gray-800 rounded-lg h-80 flex items-end justify-end p-4 relative overflow-hidden">
            <span className="text-gray-300 dark:text-gray-600 text-sm absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2">
              Tu sitio web
            </span>
            {/* Simulated popup — greeting can run up to 200 chars, so this can
                grow tall; bottom-16 + overflow-hidden on the mockup above
                keep it from overlapping the "Vista previa" label past the box. */}
            <div
              className={`absolute bottom-16 ${configData.position === 'left' ? 'left-6' : 'right-6'} w-64 rounded-2xl bg-white dark:bg-gray-950 shadow-xl border border-gray-100 dark:border-gray-800 overflow-hidden`}
            >
              <div className="flex items-center gap-2 px-4 py-3" style={{ background: configData.color }}>
                <div className="w-9 h-9 rounded-full bg-white/25 flex items-center justify-center text-lg shrink-0">🎙️</div>
                <div className="text-white text-left">
                  <p className="text-sm font-bold leading-tight">Asistente</p>
                  <p className="text-xs opacity-80">En línea</p>
                </div>
              </div>
              <div className="px-4 py-3 bg-gray-50 dark:bg-gray-900">
                <div
                  className="bg-white dark:bg-gray-950 rounded-r-xl rounded-bl-xl px-3 py-2 text-sm text-gray-700 dark:text-gray-300 shadow-sm max-w-[85%]"
                >
                  {configData.greeting}
                </div>
              </div>
              <div className="px-4 py-3 border-t border-gray-100 dark:border-gray-800">
                <a
                  className="flex items-center justify-center gap-2 py-2.5 rounded-lg text-white text-sm font-semibold"
                  style={{ background: configData.color }}
                >
                  <svg viewBox="0 0 24 24" className="w-4 h-4 fill-white"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347z"/><path d="M12 0C5.373 0 0 5.373 0 12c0 2.126.555 4.126 1.527 5.865L0 24l6.295-1.508A11.956 11.956 0 0012 24c6.627 0 12-5.373 12-12S18.627 0 12 0zm0 21.818a9.818 9.818 0 01-5.007-1.37l-.36-.213-3.735.894.944-3.646-.234-.374A9.818 9.818 0 012.182 12C2.182 6.57 6.57 2.182 12 2.182S21.818 6.57 21.818 12 17.43 21.818 12 21.818z"/></svg>
                  Chatear por WhatsApp
                </a>
              </div>
            </div>
            {/* Simulated floating button */}
            <div
              className={`absolute bottom-6 ${configData.position === 'left' ? 'left-6' : 'right-6'} w-14 h-14 rounded-full flex items-center justify-center shadow-lg cursor-pointer transition-transform hover:scale-105`}
              style={{ background: configData.color }}
            >
              <svg viewBox="0 0 24 24" className="w-8 h-8 fill-white">
                <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347z" />
                <path d="M12 0C5.373 0 0 5.373 0 12c0 2.126.555 4.126 1.527 5.865L0 24l6.295-1.508A11.956 11.956 0 0012 24c6.627 0 12-5.373 12-12S18.627 0 12 0zm0 21.818a9.818 9.818 0 01-5.007-1.37l-.36-.213-3.735.894.944-3.646-.234-.374A9.818 9.818 0 012.182 12C2.182 6.57 6.57 2.182 12 2.182S21.818 6.57 21.818 12 17.43 21.818 12 21.818z" />
              </svg>
            </div>
          </div>
        </div>

        {/* Controls */}
        <div className="space-y-5 order-1 lg:order-2">
          {/* Color — editable desde el wizard de tu página web (Paso 3), este
              color se comparte entre la burbuja del widget y el acento del
              sitio público, así que aquí solo se muestra de lectura. */}
          <div className="bg-white dark:bg-gray-950 border border-gray-200 dark:border-gray-800 rounded-xl p-5 space-y-3">
            <div className="flex items-center gap-2 text-sm font-semibold text-gray-700 dark:text-gray-300">
              <Palette size={16} />
              Color del widget
            </div>
            <div className="flex items-center gap-3">
              <span className="w-9 h-9 rounded-full border border-gray-200 dark:border-gray-800 shrink-0" style={{ background: configData.color }} />
              <span className="text-xs font-mono text-gray-500 dark:text-gray-400">{configData.color}</span>
            </div>
            <button
              type="button"
              onClick={() => setOpenWizardSignal((n) => n + 1)}
              className="text-xs text-brand-600 dark:text-brand-400 hover:underline"
            >
              Edita el color en tu página web →
            </button>
          </div>

          {/* Greeting */}
          <div className="bg-white dark:bg-gray-950 border border-gray-200 dark:border-gray-800 rounded-xl p-5 space-y-2">
            <div className="flex items-center gap-2 text-sm font-semibold text-gray-700 dark:text-gray-300">
              <MessageSquare size={16} />
              Saludo
            </div>
            <textarea
              value={configData.greeting}
              onChange={e => setForm(prev => ({ ...(prev ?? configData), greeting: e.target.value }))}
              maxLength={200}
              rows={2}
              className="w-full rounded-lg border border-gray-300 dark:border-gray-700 px-3 py-2 text-sm focus:border-brand-500 dark:focus:border-brand-400 focus:outline-none resize-none"
            />
            <p className="text-xs text-gray-400 dark:text-gray-500 text-right">{configData.greeting.length}/200</p>
          </div>

          {/* Position */}
          <div className="bg-white dark:bg-gray-950 border border-gray-200 dark:border-gray-800 rounded-xl p-5 space-y-3">
            <div className="flex items-center gap-2 text-sm font-semibold text-gray-700 dark:text-gray-300">
              <MoveHorizontal size={16} />
              Posición
            </div>
            <div className="flex gap-2">
              {(['left', 'right'] as const).map(pos => (
                <button
                  key={pos}
                  onClick={() => setForm(prev => ({ ...(prev ?? configData), position: pos }))}
                  className={`flex-1 rounded-lg py-2 text-sm font-medium border transition-colors ${
                    configData.position === pos
                      ? 'border-brand-500 dark:border-brand-400 bg-brand-50 dark:bg-brand-950/30 text-brand-700 dark:text-brand-300'
                      : 'border-gray-200 dark:border-gray-800 text-gray-500 dark:text-gray-400 hover:border-gray-300 dark:hover:border-gray-600'
                  }`}
                >
                  {pos === 'left' ? 'Izquierda' : 'Derecha'}
                </button>
              ))}
            </div>
          </div>

          {/* Save */}
          <button
            onClick={() => {
              if (!form) return
              saveMutation.mutate(form)
              setForm(null)
            }}
            disabled={!form || saveMutation.isPending}
            className="w-full flex items-center justify-center gap-2 rounded-xl bg-brand-500 dark:bg-brand-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-brand-600 dark:hover:bg-brand-500 disabled:opacity-50 transition-colors"
          >
            <Save size={16} />
            {saveMutation.isPending ? 'Guardando...' : 'Guardar cambios'}
          </button>
          {saveMutation.isSuccess && <p className="text-sm text-green-600 dark:text-green-400 font-medium text-center">✓ Widget actualizado</p>}
        </div>
      </div>

      {/* Code snippet */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-gray-800 dark:text-gray-200">Código de instalación</h2>
          <button
            onClick={handleCopy}
            disabled={isLoading || !snippet}
            className="flex items-center gap-2 text-sm px-4 py-2 bg-brand-500 dark:bg-brand-600 text-white rounded-lg hover:bg-brand-600 dark:hover:bg-brand-500 disabled:opacity-50 transition"
          >
            {copied ? <CheckCheck size={16} /> : <Copy size={16} />}
            {copied ? 'Copiado!' : 'Copiar código'}
          </button>
        </div>
        {isLoading ? (
          <div className="h-32 bg-gray-100 dark:bg-gray-800 animate-pulse rounded-lg" />
        ) : (
          <pre className="bg-gray-900 text-green-300 text-xs rounded-xl p-5 overflow-x-auto whitespace-pre-wrap leading-relaxed">
            {snippet?.snippet}
          </pre>
        )}
      </div>

      {/* Instructions */}
      <div className="bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-800 rounded-xl p-5 space-y-2">
        <h3 className="font-semibold text-blue-800 dark:text-blue-200 text-sm">Instrucciones de instalación</h3>
        <ol className="text-sm text-blue-700 dark:text-blue-300 space-y-1 list-decimal list-inside">
          <li>Copia el código de arriba.</li>
          <li>Pégalo en el HTML de tu sitio web, justo antes de la etiqueta <code className="bg-blue-100 dark:bg-blue-900/50 px-1 rounded">&lt;/body&gt;</code>.</li>
          <li>Guarda y publica tu sitio. El botón aparecerá en la esquina inferior {configData.position === 'left' ? 'izquierda' : 'derecha'}.</li>
        </ol>
        <a
          href="https://wa.me/"
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-xs text-blue-600 dark:text-blue-400 hover:underline mt-1"
        >
          <ExternalLink size={12} />
          Probar link de WhatsApp
        </a>
      </div>
    </div>
    </>
  )
}
