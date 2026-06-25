import { useState, useEffect } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import api, { getApiError } from '@/lib/api'
import { useAuth } from '@/contexts/AuthContext'
import { Settings, Save, Copy, Check, ExternalLink, Lock, CreditCard, AlertTriangle, Trash2, Plus, X, Globe, Palette, Key, Webhook } from 'lucide-react'
import SEO from '@/components/SEO'

const WEBHOOK_URL = `${import.meta.env.VITE_API_URL ?? ''}/api/v1/webhooks/twilio`

const CATEGORIES = [
  { value: 'restaurante', label: 'Restaurante / Bar / Taquería' },
  { value: 'tienda', label: 'Tienda / Ropa / Boutique' },
  { value: 'belleza', label: 'Salón de Belleza / Estética' },
  { value: 'gimnasio', label: 'Gimnasio / Fitness / Deportes' },
  { value: 'farmacia', label: 'Farmacia / Salud' },
  { value: 'ferreteria', label: 'Ferretería / Construcción' },
  { value: 'panaderia', label: 'Panadería / Pastelería / Café' },
  { value: 'corporativo', label: 'Consultoría / Servicios / Empresa' },
  { value: 'inmobiliaria', label: 'Inmobiliaria / Terrenos / Bienes Raíces' },
  { value: 'educacion', label: 'Educación / Academia / Cursos' },
  { value: 'automotriz', label: 'Automotriz / Taller / Agencia de Autos' },
  { value: 'tecnologia', label: 'Tecnología / Software / E-commerce' },
  { value: 'otro', label: 'Otro' },
]

const PERSONALITIES = [
  { value: 'friendly', label: 'Amigable y cercano' },
  { value: 'professional', label: 'Formal y profesional' },
  { value: 'funny', label: 'Divertido y casual' },
  { value: 'persuasive', label: 'Persuasivo y vendedor' },
]

const AVAILABLE_EVENTS = [
  { value: 'campaign.sent', label: 'Campaña enviada' },
  { value: 'campaign.completed', label: 'Campaña completada' },
  { value: 'campaign.failed', label: 'Campaña fallida' },
  { value: 'contact.created', label: 'Contacto creado' },
  { value: 'order.created', label: 'Pedido creado' },
]

const AVAILABLE_SCOPES = [
  { value: 'campaigns:read', label: 'Leer campañas' },
  { value: 'campaigns:write', label: 'Escribir campañas' },
  { value: 'contacts:read', label: 'Leer contactos' },
  { value: 'contacts:write', label: 'Escribir contactos' },
]

function WebhooksSection() {
  const { data: webhooks, refetch: refetchWebhooks } = useQuery({
    queryKey: ['user-webhooks'],
    queryFn: () => api.get('/user-webhooks').then(r => r.data),
  })

  const [showForm, setShowForm] = useState(false)
  const [newWh, setNewWh] = useState({ name: '', url: '', events: [] as string[] })
  const [testResult, setTestResult] = useState<{ id: string; result: { success?: boolean; error?: string } } | null>(null)

  const createMutation = useMutation({
    mutationFn: (data: typeof newWh) => api.post('/user-webhooks', data),
    onSuccess: () => { refetchWebhooks(); setShowForm(false); setNewWh({ name: '', url: '', events: [] }) },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/user-webhooks/${id}`),
    onSuccess: () => refetchWebhooks(),
  })

  const toggleMutation = useMutation({
    mutationFn: ({ id, active }: { id: string; active: boolean }) => api.patch(`/user-webhooks/${id}`, { active }),
    onSuccess: () => refetchWebhooks(),
  })

  const testMutation = useMutation({
    mutationFn: ({ id }: { id: string }) => api.post(`/user-webhooks/${id}/test`),
    onSuccess: (res, vars) => setTestResult({ id: vars.id, result: res.data }),
    onError: (err: unknown, vars) => setTestResult({ id: vars.id, result: { success: false, error: getApiError(err) } }),
  })

  const toggleEvent = (ev: string) => {
    setNewWh(prev => ({
      ...prev,
      events: prev.events.includes(ev) ? prev.events.filter(e => e !== ev) : [...prev.events, ev],
    }))
  }

  return (
    <div className="rounded-xl bg-card p-6 shadow-sm border border-border space-y-4">
      <div className="flex items-center gap-2">
        <Webhook className="h-4 w-4 text-muted-foreground" />
        <h2 className="text-base font-semibold text-foreground">Webhooks</h2>
      </div>
      <p className="text-sm text-muted-foreground">Recibe notificaciones HTTP cuando ocurran eventos en tu cuenta.</p>

      {webhooks?.map((wh: { id: string; name: string; url: string; events: string[]; active: boolean }) => (
        <div key={wh.id} className="flex items-start gap-3 rounded-lg border border-border p-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-foreground">{wh.name}</span>
              <span className={`text-xs px-1.5 py-0.5 rounded-full ${wh.active ? 'bg-green-100 text-green-700' : 'bg-muted text-muted-foreground'}`}>
                {wh.active ? 'Activo' : 'Inactivo'}
              </span>
            </div>
            <p className="text-xs text-muted-foreground font-mono truncate mt-0.5">{wh.url}</p>
            <div className="flex flex-wrap gap-1 mt-1.5">
              {wh.events.map((ev) => (
                <span key={ev} className="text-xs bg-brand-50 text-brand-600 px-1.5 py-0.5 rounded-full">
                  {ev}
                </span>
              ))}
            </div>
          </div>
          <div className="flex items-center gap-1 shrink-0">
            <button
              onClick={() => toggleMutation.mutate({ id: wh.id, active: !wh.active })}
              className={`text-xs px-2 py-1 rounded ${wh.active ? 'bg-muted text-muted-foreground hover:bg-muted' : 'bg-green-100 text-green-700 hover:bg-green-200'}`}
            >
              {wh.active ? 'Desactivar' : 'Activar'}
            </button>
            <button
              onClick={() => testMutation.mutate({ id: wh.id })}
              className="text-xs px-2 py-1 rounded bg-blue-50 text-blue-600 hover:bg-blue-100"
            >
              Test
            </button>
            <button
              onClick={() => { if (confirm('¿Eliminar webhook?')) deleteMutation.mutate(wh.id) }}
              className="text-xs px-2 py-1 rounded bg-red-50 text-red-600 hover:bg-red-100"
            >
              <Trash2 className="h-3 w-3" />
            </button>
          </div>
          {testResult && testResult.id === wh.id && (
            <div className={`text-xs mt-1 ${testResult.result.success ? 'text-green-600' : 'text-red-600'}`}>
              {testResult.result.success ? '✅ Ping exitoso' : `❌ ${testResult.result.error || 'Error'}`}
            </div>
          )}
        </div>
      ))}

      {showForm ? (
        <div className="space-y-3 rounded-lg border border-border p-4 bg-muted">
          <input
            type="text"
            placeholder="Nombre del webhook"
            value={newWh.name}
            onChange={e => setNewWh({ ...newWh, name: e.target.value })}
            className="w-full rounded-lg border border-border px-3 py-2 text-sm"
          />
          <input
            type="url"
            placeholder="https://ejemplo.com/webhook"
            value={newWh.url}
            onChange={e => setNewWh({ ...newWh, url: e.target.value })}
            className="w-full rounded-lg border border-border px-3 py-2 text-sm"
          />
          <div>
            <label className="block text-xs font-medium text-muted-foreground mb-1">Eventos</label>
            <div className="flex flex-wrap gap-2">
              {AVAILABLE_EVENTS.map(ev => (
                <label key={ev.value} className="flex items-center gap-1 text-xs">
                  <input
                    type="checkbox"
                    checked={newWh.events.includes(ev.value)}
                    onChange={() => toggleEvent(ev.value)}
                    className="rounded"
                  />
                  {ev.label}
                </label>
              ))}
            </div>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => createMutation.mutate(newWh)}
              disabled={!newWh.name || !newWh.url || createMutation.isPending}
              className="text-sm px-3 py-1.5 rounded-lg bg-brand-500 text-white hover:bg-brand-600 disabled:opacity-50"
            >
              {createMutation.isPending ? 'Creando...' : 'Crear'}
            </button>
            <button onClick={() => setShowForm(false)} className="text-sm px-3 py-1.5 rounded-lg border border-border text-muted-foreground hover:bg-muted">
              Cancelar
            </button>
          </div>
        </div>
      ) : (
        <button
          onClick={() => setShowForm(true)}
          className="inline-flex items-center gap-1 text-sm text-brand-600 hover:text-brand-700"
        >
          <Plus className="h-4 w-4" /> Agregar webhook
        </button>
      )}
    </div>
  )
}


function WhiteLabelSection() {
  const { data: wl, refetch: refetchWl } = useQuery({
    queryKey: ['white-label'],
    queryFn: () => api.get('/profile/white-label').then(r => r.data),
  })

  const [form, setForm] = useState({
    primary_color: '#6366f1',
    app_name: '',
    hide_branding: false,
    custom_domain: '',
    favicon_url: '',
  })

  useEffect(() => {
    if (wl) {
      setForm({
        primary_color: wl.primary_color || '#6366f1',
        app_name: wl.app_name || '',
        hide_branding: wl.hide_branding || false,
        custom_domain: wl.custom_domain || '',
        favicon_url: wl.favicon_url || '',
      })
    }
  }, [wl])

  const mutation = useMutation({
    mutationFn: (data: typeof form) => api.patch('/profile/white-label', data),
    onSuccess: () => {
      refetchWl()
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    },
  })

  const [saved, setSaved] = useState(false)

  return (
    <div className="rounded-xl bg-card p-6 shadow-sm border border-border space-y-4">
      <div className="flex items-center gap-2">
        <Palette className="h-4 w-4 text-muted-foreground" />
        <h2 className="text-base font-semibold text-foreground">White Label</h2>
      </div>
      <p className="text-sm text-muted-foreground">Personaliza la apariencia de tu plataforma</p>

      <div>
        <label className="block text-sm font-medium text-foreground mb-1">Color primario</label>
        <div className="flex items-center gap-2">
          <input
            type="color"
            value={form.primary_color}
            onChange={e => setForm({ ...form, primary_color: e.target.value })}
            className="h-9 w-9 rounded border border-border cursor-pointer"
          />
          <input
            type="text"
            value={form.primary_color}
            onChange={e => setForm({ ...form, primary_color: e.target.value })}
            className="flex-1 rounded-lg border border-border px-3 py-2 text-sm font-mono"
          />
        </div>
      </div>

      <div>
        <label className="block text-sm font-medium text-foreground mb-1">Nombre de la aplicación</label>
        <input
          type="text"
          value={form.app_name}
          onChange={e => setForm({ ...form, app_name: e.target.value })}
          placeholder="Ej: Mi Radio"
          className="w-full rounded-lg border border-border px-3 py-2 text-sm"
        />
      </div>

      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={form.hide_branding}
          onChange={e => setForm({ ...form, hide_branding: e.target.checked })}
          className="rounded"
        />
        <span>Ocultar marca IaRadio</span>
      </label>

      <div>
        <label className="block text-sm font-medium text-foreground mb-1">Dominio personalizado</label>
        <div className="relative">
          <input
            type="text"
            value={form.custom_domain}
            onChange={e => setForm({ ...form, custom_domain: e.target.value })}
            placeholder="ejemplo.com"
            className="w-full rounded-lg border border-border px-3 py-2 text-sm pr-24"
          />
          <span className="absolute right-2 top-1/2 -translate-y-1/2 text-xs bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded-full">
            Próximamente
          </span>
        </div>
      </div>

      <div>
        <label className="block text-sm font-medium text-foreground mb-1">URL del Favicon</label>
        <input
          type="url"
          value={form.favicon_url}
          onChange={e => setForm({ ...form, favicon_url: e.target.value })}
          placeholder="https://ejemplo.com/favicon.ico"
          className="w-full rounded-lg border border-border px-3 py-2 text-sm"
        />
      </div>

      <div className="flex items-center gap-4">
        <button
          onClick={() => mutation.mutate(form)}
          disabled={mutation.isPending}
          className="inline-flex items-center gap-2 rounded-xl bg-brand-500 px-5 py-2.5 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-60 transition-colors"
        >
          <Save className="h-4 w-4" />
          {mutation.isPending ? 'Guardando...' : 'Guardar cambios'}
        </button>
        {saved && (
          <span className="text-sm font-medium text-green-600">¡Cambios guardados correctamente!</span>
        )}
      </div>
    </div>
  )
}


function ApiKeysSection() {
  const { data: apiKeys, refetch: refetchKeys } = useQuery({
    queryKey: ['api-keys'],
    queryFn: () => api.get('/api-keys').then(r => r.data),
  })

  const [showCreate, setShowCreate] = useState(false)
  const [newKey, setNewKey] = useState({ name: '', scopes: [] as string[] })
  const [createdKey, setCreatedKey] = useState<string | null>(null)

  const createMutation = useMutation({
    mutationFn: (data: typeof newKey) => api.post('/api-keys', data),
    onSuccess: (res) => {
      setCreatedKey(res.data.key)
      setNewKey({ name: '', scopes: [] })
      refetchKeys()
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/api-keys/${id}`),
    onSuccess: () => refetchKeys(),
  })

  const deactivateMutation = useMutation({
    mutationFn: (id: string) => api.patch(`/api-keys/${id}/deactivate`),
    onSuccess: () => refetchKeys(),
  })

  const toggleScope = (scope: string) => {
    setNewKey(prev => ({
      ...prev,
      scopes: prev.scopes.includes(scope) ? prev.scopes.filter(s => s !== scope) : [...prev.scopes, scope],
    }))
  }

  const [copiedKey, setCopiedKey] = useState(false)

  return (
    <div className="rounded-xl bg-card p-6 shadow-sm border border-border space-y-4">
      <div className="flex items-center gap-2">
        <Key className="h-4 w-4 text-muted-foreground" />
        <h2 className="text-base font-semibold text-foreground">API Keys</h2>
      </div>
      <p className="text-sm text-muted-foreground">Crea y gestiona claves de API para acceder a la API pública.</p>

      {apiKeys?.map((ak: { id: string; name: string; prefix: string; scopes: string[]; active: boolean; last_used_at?: string }) => (
        <div key={ak.id} className="flex items-start gap-3 rounded-lg border border-border p-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-foreground">{ak.name}</span>
              <span className={`text-xs px-1.5 py-0.5 rounded-full ${ak.active ? 'bg-green-100 text-green-700' : 'bg-muted text-muted-foreground'}`}>
                {ak.active ? 'Activa' : 'Inactiva'}
              </span>
            </div>
            <p className="text-xs text-muted-foreground font-mono mt-0.5">{ak.prefix}...</p>
            <div className="flex flex-wrap gap-1 mt-1">
              {ak.scopes?.map((s) => (
                <span key={s} className="text-xs bg-blue-50 text-blue-600 px-1.5 py-0.5 rounded-full">{s}</span>
              ))}
            </div>
            {ak.last_used_at && (
              <p className="text-xs text-muted-foreground mt-0.5">Último uso: {new Date(ak.last_used_at).toLocaleDateString()}</p>
            )}
          </div>
          <div className="flex items-center gap-1 shrink-0">
            {ak.active && (
              <button
                onClick={() => deactivateMutation.mutate(ak.id)}
                className="text-xs px-2 py-1 rounded bg-muted text-muted-foreground hover:bg-muted"
              >
                Desactivar
              </button>
            )}
            <button
              onClick={() => { if (confirm('¿Eliminar API key?')) deleteMutation.mutate(ak.id) }}
              className="text-xs px-2 py-1 rounded bg-red-50 text-red-600 hover:bg-red-100"
            >
              <Trash2 className="h-3 w-3" />
            </button>
          </div>
        </div>
      ))}

      {createdKey && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 space-y-2">
          <div className="flex items-start gap-2">
            <AlertTriangle className="h-4 w-4 text-amber-600 shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-medium text-amber-800">¡Guarda esta clave! No se mostrará de nuevo.</p>
              <div className="flex items-center gap-2 mt-1">
                <code className="flex-1 text-xs bg-card border border-amber-200 rounded px-2 py-1 font-mono break-all">{createdKey}</code>
                <button
                  onClick={() => { navigator.clipboard.writeText(createdKey); setCopiedKey(true); setTimeout(() => setCopiedKey(false), 2000) }}
                  className="shrink-0 text-xs px-2 py-1 rounded bg-amber-600 text-white hover:bg-amber-700"
                >
                  {copiedKey ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
                </button>
              </div>
            </div>
          </div>
          <button
            onClick={() => setCreatedKey(null)}
            className="text-xs text-amber-700 underline"
          >
            Cerrar
          </button>
        </div>
      )}

      {showCreate ? (
        <div className="space-y-3 rounded-lg border border-border p-4 bg-muted">
          <input
            type="text"
            placeholder="Nombre de la API key"
            value={newKey.name}
            onChange={e => setNewKey({ ...newKey, name: e.target.value })}
            className="w-full rounded-lg border border-border px-3 py-2 text-sm"
          />
          <div>
            <label className="block text-xs font-medium text-muted-foreground mb-1">Permisos</label>
            <div className="flex flex-wrap gap-2">
              {AVAILABLE_SCOPES.map(sc => (
                <label key={sc.value} className="flex items-center gap-1 text-xs">
                  <input
                    type="checkbox"
                    checked={newKey.scopes.includes(sc.value)}
                    onChange={() => toggleScope(sc.value)}
                    className="rounded"
                  />
                  {sc.label}
                </label>
              ))}
            </div>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => createMutation.mutate(newKey)}
              disabled={!newKey.name || createMutation.isPending}
              className="text-sm px-3 py-1.5 rounded-lg bg-brand-500 text-white hover:bg-brand-600 disabled:opacity-50"
            >
              {createMutation.isPending ? 'Creando...' : 'Crear'}
            </button>
            <button onClick={() => setShowCreate(false)} className="text-sm px-3 py-1.5 rounded-lg border border-border text-muted-foreground hover:bg-muted">
              Cancelar
            </button>
          </div>
        </div>
      ) : (
        <button
          onClick={() => setShowCreate(true)}
          className="inline-flex items-center gap-1 text-sm text-brand-600 hover:text-brand-700"
        >
          <Plus className="h-4 w-4" /> Crear API key
        </button>
      )}
    </div>
  )
}


export default function SettingsPage() {
  const { user, setUser } = useAuth()
  const qc = useQueryClient()
  const [saved, setSaved] = useState(false)
  const [copied, setCopied] = useState(false)
  const [pwForm, setPwForm] = useState({ current_password: '', new_password: '', confirm_password: '' })
  const [pwMsg, setPwMsg] = useState<{ type: 'ok' | 'error'; text: string } | null>(null)

  const copyWebhook = () => {
    navigator.clipboard.writeText(WEBHOOK_URL)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const [cancelConfirm, setCancelConfirm] = useState(false)
  const [cancelDone, setCancelDone] = useState(false)

  const cancelMutation = useMutation({
    mutationFn: () => api.post('/cancel-subscription'),
    onSuccess: () => {
      setCancelDone(true)
      setCancelConfirm(false)
      qc.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })

  const { data: dashboard } = useQuery({
    queryKey: ['dashboard'],
    queryFn: () => api.get('/dashboard').then(r => r.data),
    staleTime: 60_000,
  })

  const [form, setForm] = useState({
    business_name: '',
    business_category: '',
    city: '',
    country: 'MX',
    phone: '',
    whatsapp_number: '',
    language: 'es',
    bot_name: '',
    bot_personality: 'friendly',
    bot_instructions: '',
  })

  const numberSource: string = user?.whatsapp_number_source ?? 'shared'
  const currentPlan: string = user?.current_plan ?? 'trial'
  const numberIsManaged = numberSource === 'pool'
  const showTwilioSetup = numberSource === 'own' || currentPlan === 'enterprise'

  useEffect(() => {
    if (user) {
      setForm({
        business_name: user.business_name ?? '',
        business_category: user.business_category ?? '',
        city: user.city ?? '',
        country: user.country ?? 'MX',
        phone: user.phone ?? '',
        whatsapp_number: user.whatsapp_number ?? '',
        language: user.language ?? 'es',
        bot_name: user.bot_name ?? '',
        bot_personality: user.bot_personality ?? 'friendly',
        bot_instructions: user.bot_instructions ?? '',
      })
    }
  }, [user])

  const mutation = useMutation({
    mutationFn: (data: typeof form) => api.patch('/me', data).then((r) => r.data),
    onSuccess: (updated) => {
      if (setUser) setUser(updated)
      qc.invalidateQueries({ queryKey: ['me'] })
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    },
  })

  const pwMutation = useMutation({
    mutationFn: (data: { current_password: string; new_password: string }) =>
      api.post('/me/change-password', data),
    onSuccess: () => {
      setPwMsg({ type: 'ok', text: '¡Contraseña actualizada correctamente!' })
      setPwForm({ current_password: '', new_password: '', confirm_password: '' })
      setTimeout(() => setPwMsg(null), 4000)
    },
    onError: (err: unknown) => {
      setPwMsg({ type: 'error', text: getApiError(err, 'Error al cambiar contraseña') })
    },
  })

  const field = (label: string, key: keyof typeof form, type = 'text', placeholder = '') => (
    <div>
      <label className="block text-sm font-medium text-foreground mb-1">{label}</label>
      <input
        type={type}
        value={form[key]}
        onChange={(e) => setForm({ ...form, [key]: e.target.value })}
        placeholder={placeholder}
        className="w-full rounded-lg border border-border px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none"
      />
    </div>
  )

  return (
    <>
      <SEO title="Configuración" description="Panel de control de IaRadio." noIndex />
      <div className="space-y-8 max-w-2xl">
      <div className="flex items-center gap-3">
        <div className="rounded-xl bg-brand-50 p-2.5">
          <Settings className="h-5 w-5 text-brand-500" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-foreground">Configuración</h1>
          <p className="text-sm text-muted-foreground">Ajusta los datos de tu negocio y el perfil de tu bot</p>
        </div>
      </div>

      {/* Business info */}
      <div className="rounded-xl bg-card p-6 shadow-sm border border-border space-y-4">
        <h2 className="text-base font-semibold text-foreground">Datos del negocio</h2>
        {field('Nombre del negocio', 'business_name', 'text', 'Ej: Restaurante La Paloma')}
        <div>
          <label className="block text-sm font-medium text-foreground mb-1">Categoría</label>
          <select
            value={form.business_category}
            onChange={(e) => setForm({ ...form, business_category: e.target.value })}
            className="w-full rounded-lg border border-border px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none bg-card"
          >
            <option value="">Seleccionar...</option>
            {CATEGORIES.map((c) => (
              <option key={c.value} value={c.value}>{c.label}</option>
            ))}
          </select>
        </div>
        <div className="grid grid-cols-2 gap-4">
          {field('Ciudad', 'city', 'text', 'Ej: Ciudad de México')}
          {field('País (código)', 'country', 'text', 'Ej: MX')}
        </div>
        {field('Teléfono', 'phone', 'tel', 'Ej: +525512345678')}
        <div>
          <label className="block text-sm font-medium text-foreground mb-1">
            Número WhatsApp Business
            {numberIsManaged && (
              <span className="ml-1.5 rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">Asignado por IaRadio</span>
            )}
          </label>
          {numberIsManaged ? (
            <div className="flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 px-3.5 py-2.5">
              <span className="flex-1 text-sm font-mono text-green-800">{form.whatsapp_number || '—'}</span>
              <span className="text-xs text-green-600">Tu número dedicado ✅</span>
            </div>
          ) : (
            <>
              <input
                type="tel"
                value={form.whatsapp_number}
                onChange={(e) => setForm({ ...form, whatsapp_number: e.target.value })}
                placeholder="Ej: +525512345678 (solo si tienes WABA propio)"
                className="w-full rounded-lg border border-border px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none"
              />
              {numberSource === 'shared' && (
                <p className="mt-1 text-xs text-muted-foreground">
                  En el plan actual usas el número compartido de IaRadio.
                  Al subir al plan <strong>Pro</strong> se te asigna un número dedicado automáticamente.
                </p>
              )}
            </>
          )}
        </div>
      </div>

      {/* Twilio webhook setup — only for Enterprise / own WABA users */}
      {showTwilioSetup && <div className="rounded-xl bg-amber-50 border border-amber-200 p-6 space-y-3">
        <h2 className="text-base font-semibold text-amber-900">Configuración Twilio (WhatsApp Business)</h2>
        <p className="text-sm text-amber-800">
          Para que tu bot responda mensajes entrantes, configura esta URL en tu consola de Twilio:
          <br />
          <span className="font-medium">Messaging → Sender → Webhook URL (Incoming Message)</span>
        </p>
        <div className="flex items-center gap-2">
          <code className="flex-1 rounded-lg bg-card border border-amber-200 px-3 py-2 text-xs font-mono text-foreground break-all">
            {WEBHOOK_URL}
          </code>
          <button
            onClick={copyWebhook}
            className="shrink-0 flex items-center gap-1.5 rounded-lg border border-amber-300 bg-card px-3 py-2 text-xs font-medium text-amber-700 hover:bg-amber-50 transition-colors"
          >
            {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
            {copied ? 'Copiado' : 'Copiar'}
          </button>
        </div>
        <a
          href="https://console.twilio.com/us1/develop/sms/try-it-out/whatsapp-learn"
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-xs text-amber-700 underline hover:text-amber-900"
        >
          <ExternalLink className="h-3 w-3" />
          Ver guía en Twilio Console
        </a>
      </div>}

      {/* Bot config */}
      <div className="rounded-xl bg-card p-6 shadow-sm border border-border space-y-4">
        <h2 className="text-base font-semibold text-foreground">Configuración del bot</h2>
        <p className="text-sm text-muted-foreground">
          El bot de WhatsApp usará este nombre y personalidad para responder a tus clientes.
        </p>
        {field('Nombre del bot', 'bot_name', 'text', 'Ej: Sofía, Carlos, Asistente')}
        <div>
          <label className="block text-sm font-medium text-foreground mb-1">Personalidad</label>
          <select
            value={form.bot_personality}
            onChange={(e) => setForm({ ...form, bot_personality: e.target.value })}
            className="w-full rounded-lg border border-border px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none bg-card"
          >
            {PERSONALITIES.map((p) => (
              <option key={p.value} value={p.value}>{p.label}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium text-foreground mb-1">Idioma</label>
          <select
            value={form.language}
            onChange={(e) => setForm({ ...form, language: e.target.value })}
            className="w-full rounded-lg border border-border px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none bg-card"
          >
            <option value="es">Español</option>
            <option value="en">English</option>
            <option value="pt">Português</option>
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium text-foreground mb-1">Instrucciones personalizadas</label>
          <p className="text-xs text-muted-foreground mb-2">
            Estas instrucciones tienen prioridad sobre cualquier otra regla. Úsalas para definir comportamientos específicos del bot.
          </p>
          <textarea
            value={form.bot_instructions}
            onChange={(e) => setForm({ ...form, bot_instructions: e.target.value })}
            rows={4}
            className="w-full rounded-lg border border-border px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none bg-card resize-y"
            placeholder="Ej: Si preguntan por precio, ofrece un 10% de descuento por primera compra. Deriva a enlace de pago si confirman el pedido."
          />
        </div>
      </div>

      <div className="flex items-center gap-4">
        <button
          onClick={() => mutation.mutate(form)}
          disabled={mutation.isPending}
          className="inline-flex items-center gap-2 rounded-xl bg-brand-500 px-5 py-2.5 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-60 transition-colors"
        >
          <Save className="h-4 w-4" />
          {mutation.isPending ? 'Guardando...' : 'Guardar cambios'}
        </button>
        {saved && (
          <span className="text-sm font-medium text-green-600">¡Cambios guardados correctamente!</span>
        )}
        {mutation.isError && (
          <span className="text-sm text-red-600">
            {(mutation.error && 'response' in mutation.error ? (mutation.error as { response: { data: { detail: string } } }).response.data.detail : null) ?? 'Error al guardar'}
          </span>
        )}
      </div>

      {/* Subscription */}
      {dashboard && (
        <div className="rounded-xl bg-card p-6 shadow-sm border border-border space-y-4">
          <div className="flex items-center gap-2">
            <CreditCard className="h-4 w-4 text-muted-foreground" />
            <h2 className="text-base font-semibold text-foreground">Suscripción</h2>
          </div>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="text-muted-foreground">Plan</span>
              <p className="font-medium capitalize">{dashboard.plan}</p>
            </div>
            <div>
              <span className="text-muted-foreground">Estado</span>
              <p className={`font-medium capitalize ${dashboard.subscription_status === 'active' ? 'text-green-600' : 'text-yellow-600'}`}>
                {dashboard.subscription_status === 'active' ? 'Activa' : dashboard.subscription_status === 'trial' ? 'Prueba' : 'Inactiva'}
              </p>
            </div>
            <div>
              <span className="text-muted-foreground">Mensajes restantes</span>
              <p className="font-medium">{dashboard.messages_remaining}</p>
            </div>
          </div>
          {dashboard.subscription_status === 'active' && !cancelDone && (
            <div className="pt-2">
              {cancelConfirm ? (
                <div className="flex items-center gap-3 p-3 rounded-lg bg-red-50 border border-red-200">
                  <AlertTriangle className="h-5 w-5 text-red-500 shrink-0" />
                  <p className="text-sm text-red-700 flex-1">¿Cancelar suscripción? Seguirás con acceso hasta el fin del período pagado.</p>
                  <button
                    onClick={() => cancelMutation.mutate()}
                    disabled={cancelMutation.isPending}
                    className="text-sm px-3 py-1.5 rounded-lg bg-red-600 text-white hover:bg-red-700 disabled:opacity-50"
                  >
                    {cancelMutation.isPending ? 'Cancelando...' : 'Sí, cancelar'}
                  </button>
                  <button
                    onClick={() => setCancelConfirm(false)}
                    className="text-sm px-3 py-1.5 rounded-lg border border-border text-muted-foreground hover:bg-muted"
                  >
                    No
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => setCancelConfirm(true)}
                  className="text-sm text-red-600 hover:text-red-700 underline underline-offset-2"
                >
                  Cancelar suscripción
                </button>
              )}
            </div>
          )}
          {cancelDone && (
            <p className="text-sm text-green-600 font-medium">Suscripción cancelada. Seguirás teniendo acceso hasta el final del período de facturación.</p>
          )}
        </div>
      )}

      {/* Change password */}
      <div className="rounded-xl bg-card p-6 shadow-sm border border-border space-y-4">
        <div className="flex items-center gap-2">
          <Lock className="h-4 w-4 text-muted-foreground" />
          <h2 className="text-base font-semibold text-foreground">Cambiar contraseña</h2>
        </div>
        <div className="space-y-3">
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Contraseña actual</label>
            <input
              type="password"
              value={pwForm.current_password}
              onChange={(e) => setPwForm({ ...pwForm, current_password: e.target.value })}
              placeholder="••••••••"
              className="w-full rounded-lg border border-border px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Nueva contraseña</label>
            <input
              type="password"
              value={pwForm.new_password}
              onChange={(e) => setPwForm({ ...pwForm, new_password: e.target.value })}
              placeholder="Mínimo 8 caracteres"
              className="w-full rounded-lg border border-border px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Confirmar nueva contraseña</label>
            <input
              type="password"
              value={pwForm.confirm_password}
              onChange={(e) => setPwForm({ ...pwForm, confirm_password: e.target.value })}
              placeholder="Repite la nueva contraseña"
              className="w-full rounded-lg border border-border px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none"
            />
          </div>
        </div>
        <div className="flex items-center gap-4">
          <button
            onClick={() => {
              if (pwForm.new_password !== pwForm.confirm_password) {
                setPwMsg({ type: 'error', text: 'Las contraseñas no coinciden' })
                return
              }
              pwMutation.mutate({ current_password: pwForm.current_password, new_password: pwForm.new_password })
            }}
            disabled={pwMutation.isPending || !pwForm.current_password || !pwForm.new_password}
            className="inline-flex items-center gap-2 rounded-xl border border-border px-4 py-2 text-sm font-medium text-foreground hover:bg-muted disabled:opacity-50 transition-colors"
          >
            <Lock className="h-4 w-4" />
            {pwMutation.isPending ? 'Actualizando...' : 'Actualizar contraseña'}
          </button>
          {pwMsg && (
            <span className={`text-sm font-medium ${pwMsg.type === 'ok' ? 'text-green-600' : 'text-red-600'}`}>
              {pwMsg.text}
            </span>
          )}
        </div>
      </div>

      {/* Webhooks */}
      <WebhooksSection />

      {/* White Label */}
      <WhiteLabelSection />

      {/* API Keys */}
      <ApiKeysSection />

      {/* Music attribution — required by Kevin MacLeod CC BY 3.0 */}
      <div className="rounded-xl border border-border bg-muted px-6 py-4">
        <p className="text-xs text-muted-foreground">
          Música de fondo para anuncios:{' '}
          <a
            href="https://incompetech.com"
            target="_blank"
            rel="noopener noreferrer"
            className="underline hover:text-muted-foreground"
          >
            Kevin MacLeod
          </a>{' '}
          (incompetech.com). Licencia{' '}
          <a
            href="https://creativecommons.org/licenses/by/3.0/"
            target="_blank"
            rel="noopener noreferrer"
            className="underline hover:text-muted-foreground"
          >
            CC BY 3.0
          </a>
          .
        </p>
      </div>
    </div>
    </>
  )
}
