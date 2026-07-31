import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import api, { getApiError } from '@/lib/api'
import { Check, Loader2, MessageCircle, X } from 'lucide-react'

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

  const [wabaId, setWabaId] = useState('')
  const [phoneNumberId, setPhoneNumberId] = useState('')
  const [token, setToken] = useState('')
  const [testResult, setTestResult] = useState<TestResult | null>(null)

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

      <p className="text-xs text-muted-foreground">
        Obtén estos datos en{' '}
        <a href="https://developers.facebook.com" target="_blank" rel="noreferrer" className="underline">
          developers.facebook.com
        </a>{' '}
        → tu app → WhatsApp → API Setup. El token debe ser de un usuario del sistema (no expira).
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
