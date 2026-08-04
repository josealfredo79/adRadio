import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import api, { getApiError } from '@/lib/api'
import { launchEmbeddedSignup } from '@/lib/fbSdk'
import { Check, ChevronDown, ExternalLink, Loader2, MessageCircle, X } from 'lucide-react'

// Embedded Signup requiere que la app esté certificada como Tech Provider/BSP
// ante Meta (bloqueado hasta que se apruebe — ver memoria de sesión 2026-08-04).
// El código queda intacto y probado; solo se oculta del dashboard hasta entonces.
const EMBEDDED_SIGNUP_LIVE = false

interface Connection {
  waba_id: string | null
  phone_number_id: string | null
  display_phone_number: string | null
  verified_name: string | null
  status: string
  token_last4: string | null
  utility_template_status: string
  utility_template_name: string | null
  appointment_template_name: string | null
}

interface TestResult {
  ok: boolean
  display_phone_number?: string | null
  verified_name?: string | null
  message?: string | null
}

export default function WhatsappWizard() {
  const qc = useQueryClient()
  const { data: connection } = useQuery<Connection>({
    queryKey: ['whatsapp-connection'],
    queryFn: () => api.get('/me/whatsapp-connection').then((r) => r.data),
  })
  const { data: embeddedConfig } = useQuery<{ app_id: string; config_id: string; enabled: boolean }>({
    queryKey: ['whatsapp-embedded-config'],
    queryFn: () => api.get('/me/whatsapp-embedded-config').then((r) => r.data),
    staleTime: 60_000,
  })
  const [connectError, setConnectError] = useState<string | null>(null)

  const embeddedMutation = useMutation({
    mutationFn: ({ code, wabaId, phoneNumberId }: { code: string; wabaId: string; phoneNumberId: string }) =>
      api
        .post('/me/whatsapp-connection/embedded', {
          code,
          waba_id: wabaId,
          phone_number_id: phoneNumberId,
        })
        .then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['whatsapp-connection'] })
    },
    onError: (err: unknown) => setConnectError(getApiError(err, 'No se pudo completar la conexión con Meta')),
  })

  const handleConnectWithMeta = async () => {
    setConnectError(null)
    if (!embeddedConfig?.app_id || !embeddedConfig?.config_id) {
      setConnectError('El servidor aún no tiene configurado "Conectar con Meta". Usa el formulario manual o revisa META_APP_ID/META_EMBEDDED_SIGNUP_CONFIG_ID.')
      return
    }
    try {
      const result = await launchEmbeddedSignup(embeddedConfig.app_id, embeddedConfig.config_id)
      if (!result.wabaId || !result.phoneNumberId) {
        setConnectError('Meta no devolvió el número seleccionado. Intenta de nuevo o usa el formulario manual.')
        return
      }
      await embeddedMutation.mutateAsync(result)
    } catch (err) {
      setConnectError(err instanceof Error ? err.message : 'No se pudo completar la conexión con Meta')
    }
  }

  const [wabaId, setWabaId] = useState('')
  const [phoneNumberId, setPhoneNumberId] = useState('')
  const [token, setToken] = useState('')
  const [testResult, setTestResult] = useState<TestResult | null>(null)
  const [showGuide, setShowGuide] = useState(false)

  const canTest = wabaId.trim() && phoneNumberId.trim() && token.trim()

  const testMutation = useMutation({
    mutationFn: () =>
      api
        .post('/me/whatsapp-connection/test', { waba_id: wabaId, phone_number_id: phoneNumberId, token })
        .then((r) => r.data as TestResult),
    onSuccess: (data) => setTestResult(data),
    onError: (err: unknown) => setTestResult({ ok: false, message: getApiError(err, 'No se pudo probar la conexión') }),
  })

  const saveMutation = useMutation({
    mutationFn: () =>
      api.put('/me/whatsapp-connection', { waba_id: wabaId, phone_number_id: phoneNumberId, token }).then((r) => r.data),
    onSuccess: () => {
      setToken('')
      setTestResult(null)
      qc.invalidateQueries({ queryKey: ['whatsapp-connection'] })
    },
  })

  const templatesMutation = useMutation({
    mutationFn: (body: { utility_template_name?: string; appointment_template_name?: string }) =>
      api.patch('/me/whatsapp-templates', body).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['whatsapp-connection'] }),
  })

  const [utilityTemplate, setUtilityTemplate] = useState(connection?.utility_template_name ?? '')
  const [apptTemplate, setApptTemplate] = useState(connection?.appointment_template_name ?? '')

  const isConnected = connection?.status === 'connected'

  return (
    <div className="rounded-xl bg-card p-6 shadow-sm border border-border space-y-5">
      <div className="flex items-center gap-2">
        <MessageCircle className="h-5 w-5 text-brand-500" />
        <h2 className="text-base font-semibold text-foreground">WhatsApp Business (Meta Cloud API)</h2>
      </div>

      {isConnected && (
        <div className="flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 px-3.5 py-2.5">
          <Check className="h-4 w-4 text-green-600 shrink-0" />
          <div className="text-sm text-green-800">
            <span className="font-medium">{connection?.display_phone_number}</span>
            {connection?.verified_name ? ` — ${connection.verified_name}` : ''}
            {connection?.token_last4 && (
              <span className="text-green-600"> · token termina en {connection.token_last4}</span>
            )}
          </div>
        </div>
      )}
      {connection?.status === 'reconnect_required' && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-3.5 py-2.5 text-sm text-amber-800">
          El token expiró o ya no es válido — reconecta abajo.
        </div>
      )}

      {EMBEDDED_SIGNUP_LIVE && (
        <div className="rounded-lg border border-border bg-muted/30 p-4 space-y-3">
          <p className="text-sm font-medium text-foreground">
            ¿Ya tienes tu cuenta de negocio en Meta? Conecta en un solo clic.
          </p>
          <button
            type="button"
            onClick={handleConnectWithMeta}
            disabled={embeddedMutation.isPending}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-[#1877F2] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[#0f68d9] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {embeddedMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <svg className="h-4 w-4" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z" />
              </svg>
            )}
            {embeddedMutation.isPending ? 'Conectando con Meta…' : 'Conectar con Meta'}
          </button>
          <p className="text-xs text-muted-foreground">
            Se abrirá una ventana de Meta: inicia sesión, elige tu negocio y tu número. El token y la
            configuración se hacen solos — no necesitas pegar nada.
          </p>
          {connectError && (
            <p className="text-sm text-red-600">{connectError}</p>
          )}
        </div>
      )}

      <button
        type="button"
        onClick={() => setShowGuide((v) => !v)}
        className="flex w-full items-center justify-between rounded-lg border border-border bg-muted/50 px-3.5 py-2.5 text-sm font-medium text-foreground hover:bg-muted transition-colors"
      >
        <span>Guía paso a paso (cómo conseguir estos datos)</span>
        <ChevronDown className={`h-4 w-4 text-muted-foreground transition-transform ${showGuide ? 'rotate-180' : ''}`} />
      </button>

      {showGuide && (
        <ol className="space-y-4 rounded-lg border border-border p-4 text-sm text-foreground">
          <li className="flex gap-3">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-500 text-xs font-semibold text-white">1</span>
            <div className="space-y-1">
              <p className="font-medium">
                Crea tu cuenta de negocio (si no la tienes) y agrega WhatsApp
              </p>
              <p className="text-xs text-muted-foreground">
                Entra a{' '}
                <a href="https://business.facebook.com" target="_blank" rel="noreferrer" className="underline">
                  business.facebook.com
                </a>{' '}
                con tu cuenta personal. Crea un Business Manager (o entra al tuyo) → en la barra lateral busca{' '}
                <span className="font-medium">WhatsApp</span> →{' '}
                <span className="font-medium">Empezar a usar</span>. Esto crea tu WhatsApp Business Account (WABA) gratis.
              </p>
            </div>
          </li>
          <li className="flex gap-3">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-500 text-xs font-semibold text-white">2</span>
            <div className="space-y-1">
              <p className="font-medium">Agrega tu número de teléfono</p>
              <p className="text-xs text-muted-foreground">
                Dentro de la WABA → <span className="font-medium">Configuración de números de teléfono</span> →{' '}
                <span className="font-medium">Agregar número</span>. Usa un número <span className="font-medium">libre de WhatsApp</span> (otro chip).
                Verifícalo con el código por SMS o llamada que te llega a ese número.
              </p>
            </div>
          </li>
          <li className="flex gap-3">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-500 text-xs font-semibold text-white">3</span>
            <div className="space-y-1">
              <p className="font-medium">Crea tu app en Meta for Developers</p>
              <p className="text-xs text-muted-foreground">
                En{' '}
                <a href="https://developers.facebook.com" target="_blank" rel="noreferrer" className="underline">
                  developers.facebook.com
                </a>{' '}
                → <span className="font-medium">Mis apps</span> → <span className="font-medium">Crear app</span> (tipo 'Negocio', luego
                agrega el producto <span className="font-medium">WhatsApp</span>). Ahí verás{' '}
                <span className="font-medium">WABA ID</span> y <span className="font-medium">Phone Number ID</span> en la sección{' '}
                <span className="font-medium">API Setup</span>.
              </p>
            </div>
          </li>
          <li className="flex gap-3">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-500 text-xs font-semibold text-white">4</span>
            <div className="space-y-1">
              <p className="font-medium">Genera el token permanente</p>
              <p className="text-xs text-muted-foreground">
                En{' '}
                <a href="https://business.facebook.com/settings/system-users" target="_blank" rel="noreferrer" className="underline">
                  business.facebook.com → Configuración → Usuarios del sistema
                </a>{' '}
                crea un usuario del sistema con tu app y permiso{' '}
                <span className="font-medium">whatsapp_business_messaging</span> y{' '}
                <span className="font-medium">whatsapp_business_management</span>, luego{' '}
                <span className="font-medium">Generar token</span> (elige tu app, sin expiración). Ese token de larga duración es el que pegas aquí.
              </p>
            </div>
          </li>
          <li className="flex gap-3">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-500 text-xs font-semibold text-white">5</span>
            <div className="space-y-1">
              <p className="font-medium">Pega los 3 datos abajo y dale 'Probar conexión'</p>
              <p className="text-xs text-muted-foreground">
                El botón de prueba valida el token contra Meta sin guardar nada. Si todo sale bien, guarda. Listo.
              </p>
            </div>
          </li>
          <li className="flex items-center gap-2 text-xs text-muted-foreground">
            <ExternalLink className="h-3.5 w-3.5 shrink-0" />
            <span>
              Guía oficial:{' '}
              <a
                href="https://developers.facebook.com/docs/whatsapp/cloud-api/get-started"
                target="_blank"
                rel="noreferrer"
                className="underline"
              >
                developers.facebook.com/docs/whatsapp/cloud-api/get-started
              </a>
            </span>
          </li>
        </ol>
      )}

      <p className="text-xs text-muted-foreground">
        Pega abajo los 3 datos que viste en el paso 3 y 4. El token debe ser de un usuario del sistema (no expira).
      </p>

      <div className="space-y-3">
        <div>
          <label className="block text-sm font-medium text-foreground mb-1">WABA ID</label>
          <input
            type="text"
            value={wabaId}
            onChange={(e) => { setWabaId(e.target.value); setTestResult(null) }}
            placeholder="Ej: 123456789012345"
            className="w-full rounded-lg border border-border bg-background text-foreground px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-foreground mb-1">Phone Number ID</label>
          <input
            type="text"
            value={phoneNumberId}
            onChange={(e) => { setPhoneNumberId(e.target.value); setTestResult(null) }}
            placeholder="Ej: 109876543210987"
            className="w-full rounded-lg border border-border bg-background text-foreground px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-foreground mb-1">Token de acceso</label>
          <input
            type="password"
            value={token}
            onChange={(e) => { setToken(e.target.value); setTestResult(null) }}
            placeholder="EAAG..."
            className="w-full rounded-lg border border-border bg-background text-foreground px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none"
          />
        </div>
      </div>

      {testResult && (
        <div
          className={`flex items-center gap-2 rounded-lg px-3.5 py-2.5 text-sm ${
            testResult.ok ? 'border border-green-200 bg-green-50 text-green-800' : 'border border-red-200 bg-red-50 text-red-800'
          }`}
        >
          {testResult.ok ? <Check className="h-4 w-4 shrink-0" /> : <X className="h-4 w-4 shrink-0" />}
          {testResult.ok
            ? `✓ Token válido para ${testResult.display_phone_number}${testResult.verified_name ? ` (${testResult.verified_name})` : ''}`
            : testResult.message}
        </div>
      )}

      <div className="flex gap-3">
        <button
          onClick={() => testMutation.mutate()}
          disabled={!canTest || testMutation.isPending}
          className="flex items-center gap-1.5 rounded-lg border border-border px-4 py-2 text-sm font-medium text-foreground hover:bg-muted disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {testMutation.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          Probar conexión
        </button>
        <button
          onClick={() => saveMutation.mutate()}
          disabled={!testResult?.ok || saveMutation.isPending}
          className="flex items-center gap-1.5 rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {saveMutation.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          Guardar conexión
        </button>
      </div>
      {saveMutation.isError && (
        <p className="text-sm text-red-600">{getApiError(saveMutation.error, 'No se pudo guardar la conexión')}</p>
      )}

      {isConnected && (
        <div className="border-t border-border pt-4 space-y-3">
          <h3 className="text-sm font-semibold text-foreground">Plantillas aprobadas (opcional)</h3>
          <p className="text-xs text-muted-foreground">
            Pega el nombre exacto de las plantillas ya aprobadas en tu WhatsApp Manager. Sin esto, los
            mensajes fuera de la ventana de 24h (recordatorios, reapertura de conversación) se degradan a
            texto plano.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-foreground mb-1">Plantilla de utilidad</label>
              <input
                type="text"
                value={utilityTemplate}
                onChange={(e) => setUtilityTemplate(e.target.value)}
                onBlur={() => templatesMutation.mutate({ utility_template_name: utilityTemplate })}
                placeholder="Ej: notificacion_informativa"
                className="w-full rounded-lg border border-border bg-background text-foreground px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-foreground mb-1">Plantilla de citas</label>
              <input
                type="text"
                value={apptTemplate}
                onChange={(e) => setApptTemplate(e.target.value)}
                onBlur={() => templatesMutation.mutate({ appointment_template_name: apptTemplate })}
                placeholder="Ej: recordatorio_cita"
                className="w-full rounded-lg border border-border bg-background text-foreground px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
