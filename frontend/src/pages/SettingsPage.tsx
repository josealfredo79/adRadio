import { useState, useEffect } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api'
import { useAuth } from '@/contexts/AuthContext'
import { Settings, Save, Copy, Check, ExternalLink, Lock } from 'lucide-react'

const WEBHOOK_URL = 'https://api.iaradio.app/api/v1/webhooks/twilio'

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
  })

  const numberSource: string = (user as any)?.whatsapp_number_source ?? 'shared'
  const currentPlan: string = (user as any)?.current_plan ?? 'trial'
  const numberIsManaged = numberSource === 'pool'
  const showTwilioSetup = numberSource === 'own' || currentPlan === 'enterprise'

  useEffect(() => {
    if (user) {
      setForm({
        business_name: user.business_name ?? '',
        business_category: (user as any).business_category ?? '',
        city: (user as any).city ?? '',
        country: (user as any).country ?? 'MX',
        phone: (user as any).phone ?? '',
        whatsapp_number: (user as any).whatsapp_number ?? '',
        language: (user as any).language ?? 'es',
        bot_name: (user as any).bot_name ?? '',
        bot_personality: (user as any).bot_personality ?? 'friendly',
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
    onError: (err: any) => {
      setPwMsg({ type: 'error', text: err.response?.data?.detail ?? 'Error al cambiar contraseña' })
    },
  })

  const field = (label: string, key: keyof typeof form, type = 'text', placeholder = '') => (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
      <input
        type={type}
        value={form[key]}
        onChange={(e) => setForm({ ...form, [key]: e.target.value })}
        placeholder={placeholder}
        className="w-full rounded-lg border border-gray-300 px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none"
      />
    </div>
  )

  return (
    <div className="space-y-8 max-w-2xl">
      <div className="flex items-center gap-3">
        <div className="rounded-xl bg-brand-50 p-2.5">
          <Settings className="h-5 w-5 text-brand-500" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Configuración</h1>
          <p className="text-sm text-gray-500">Ajusta los datos de tu negocio y el perfil de tu bot</p>
        </div>
      </div>

      {/* Business info */}
      <div className="rounded-xl bg-white p-6 shadow-sm border border-gray-100 space-y-4">
        <h2 className="text-base font-semibold text-gray-900">Datos del negocio</h2>
        {field('Nombre del negocio', 'business_name', 'text', 'Ej: Restaurante La Paloma')}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Categoría</label>
          <select
            value={form.business_category}
            onChange={(e) => setForm({ ...form, business_category: e.target.value })}
            className="w-full rounded-lg border border-gray-300 px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none bg-white"
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
          <label className="block text-sm font-medium text-gray-700 mb-1">
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
                className="w-full rounded-lg border border-gray-300 px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none"
              />
              {numberSource === 'shared' && (
                <p className="mt-1 text-xs text-gray-400">
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
          <code className="flex-1 rounded-lg bg-white border border-amber-200 px-3 py-2 text-xs font-mono text-gray-800 break-all">
            {WEBHOOK_URL}
          </code>
          <button
            onClick={copyWebhook}
            className="shrink-0 flex items-center gap-1.5 rounded-lg border border-amber-300 bg-white px-3 py-2 text-xs font-medium text-amber-700 hover:bg-amber-50 transition-colors"
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
      <div className="rounded-xl bg-white p-6 shadow-sm border border-gray-100 space-y-4">
        <h2 className="text-base font-semibold text-gray-900">Configuración del bot</h2>
        <p className="text-sm text-gray-500">
          El bot de WhatsApp usará este nombre y personalidad para responder a tus clientes.
        </p>
        {field('Nombre del bot', 'bot_name', 'text', 'Ej: Sofía, Carlos, Asistente')}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Personalidad</label>
          <select
            value={form.bot_personality}
            onChange={(e) => setForm({ ...form, bot_personality: e.target.value })}
            className="w-full rounded-lg border border-gray-300 px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none bg-white"
          >
            {PERSONALITIES.map((p) => (
              <option key={p.value} value={p.value}>{p.label}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Idioma</label>
          <select
            value={form.language}
            onChange={(e) => setForm({ ...form, language: e.target.value })}
            className="w-full rounded-lg border border-gray-300 px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none bg-white"
          >
            <option value="es">Español</option>
            <option value="en">English</option>
            <option value="pt">Português</option>
          </select>
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
            {(mutation.error as any)?.response?.data?.detail ?? 'Error al guardar'}
          </span>
        )}
      </div>

      {/* Change password */}
      <div className="rounded-xl bg-white p-6 shadow-sm border border-gray-100 space-y-4">
        <div className="flex items-center gap-2">
          <Lock className="h-4 w-4 text-gray-400" />
          <h2 className="text-base font-semibold text-gray-900">Cambiar contraseña</h2>
        </div>
        <div className="space-y-3">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Contraseña actual</label>
            <input
              type="password"
              value={pwForm.current_password}
              onChange={(e) => setPwForm({ ...pwForm, current_password: e.target.value })}
              placeholder="••••••••"
              className="w-full rounded-lg border border-gray-300 px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Nueva contraseña</label>
            <input
              type="password"
              value={pwForm.new_password}
              onChange={(e) => setPwForm({ ...pwForm, new_password: e.target.value })}
              placeholder="Mínimo 8 caracteres"
              className="w-full rounded-lg border border-gray-300 px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Confirmar nueva contraseña</label>
            <input
              type="password"
              value={pwForm.confirm_password}
              onChange={(e) => setPwForm({ ...pwForm, confirm_password: e.target.value })}
              placeholder="Repite la nueva contraseña"
              className="w-full rounded-lg border border-gray-300 px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none"
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
            className="inline-flex items-center gap-2 rounded-xl border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 transition-colors"
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

      {/* Music attribution — required by Kevin MacLeod CC BY 3.0 */}
      <div className="rounded-xl border border-gray-100 bg-gray-50 px-6 py-4">
        <p className="text-xs text-gray-400">
          Música de fondo para anuncios:{' '}
          <a
            href="https://incompetech.com"
            target="_blank"
            rel="noopener noreferrer"
            className="underline hover:text-gray-600"
          >
            Kevin MacLeod
          </a>{' '}
          (incompetech.com). Licencia{' '}
          <a
            href="https://creativecommons.org/licenses/by/3.0/"
            target="_blank"
            rel="noopener noreferrer"
            className="underline hover:text-gray-600"
          >
            CC BY 3.0
          </a>
          .
        </p>
      </div>
    </div>
  )
}
