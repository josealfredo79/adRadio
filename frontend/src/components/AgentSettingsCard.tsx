import { useMutation, useQueryClient } from '@tanstack/react-query'
import api, { getApiError } from '@/lib/api'
import { useAuth } from '@/contexts/AuthContext'
import { ExternalLink, Sparkles } from 'lucide-react'
import { useState } from 'react'

/** Abre la tarjeta del dueño como cliente de su propio negocio (/c/...): ahí
 * sí entra el agente. La vista previa del widget y la página pública son
 * anónimas y el agente solo atiende a clientes identificados. */
export function AgentTestButton({ className = '' }: { className?: string }) {
  const [error, setError] = useState<string | null>(null)
  const [opening, setOpening] = useState(false)
  const open = async () => {
    setError(null)
    setOpening(true)
    // La pestaña se abre antes del await: si no, el navegador la bloquea como popup.
    const tab = window.open('', '_blank')
    try {
      const r = await api.post<{ url: string }>('/me/agent-test-link')
      if (tab) tab.location.href = r.data.url
      else window.location.href = r.data.url
    } catch (e) {
      tab?.close()
      setError(getApiError(e, 'No se pudo abrir la prueba'))
    } finally {
      setOpening(false)
    }
  }
  return (
    <div className={className}>
      <button
        type="button"
        onClick={() => void open()}
        disabled={opening}
        className="inline-flex items-center gap-1.5 rounded-lg border border-brand-200 px-3 py-1.5 text-sm font-medium text-brand-700 hover:bg-brand-50 disabled:opacity-60 dark:border-brand-800 dark:text-brand-300 dark:hover:bg-brand-950/40"
      >
        <ExternalLink className="h-4 w-4" />
        {opening ? 'Abriendo…' : 'Probar como cliente'}
      </button>
      {error && <p className="mt-1 text-sm text-red-600">{error}</p>}
    </div>
  )
}

// Agente inteligente (beta) — backend: services/customer_agent.py. En el chat
// web del cliente, en vez de pasos fijos, entiende lo que le piden y lo hace
// (siempre pidiendo confirmación antes de agendar, cambiar, cancelar o pedir).
export default function AgentSettingsCard() {
  const { user, setUser } = useAuth()
  const qc = useQueryClient()
  const mutation = useMutation({
    mutationFn: (enabled: boolean) => api.patch('/me', { customer_agent_enabled: enabled }).then((r) => r.data),
    onSuccess: (updated) => {
      setUser?.(updated)
      qc.invalidateQueries({ queryKey: ['me'] })
    },
  })

  return (
    <div className="rounded-xl bg-card p-6 shadow-sm border border-border space-y-3">
      <div className="flex items-center gap-2">
        <Sparkles className="h-5 w-5 text-brand-500" />
        <h2 className="text-base font-semibold text-foreground">Agente inteligente</h2>
        <span className="rounded-full bg-brand-50 px-2 py-0.5 text-xs font-medium text-brand-600 dark:bg-brand-950/40 dark:text-brand-300">
          Beta
        </span>
      </div>
      <p className="text-sm text-muted-foreground">
        En el chat web de tus clientes, tu asistente entiende peticiones completas — "¿tienes lugar el viernes en la
        tarde?", "cámbiame la cita al sábado", "mándame 2 de pastor a domicilio" — y las resuelve: busca horarios,
        agenda, mueve o cancela citas, arma pedidos y revisa sellos. Siempre le pregunta al cliente antes de hacer algo.
        Las preguntas sencillas se siguen contestando igual que hoy.
      </p>
      <label className="flex items-center gap-2 text-sm font-medium text-foreground">
        <input
          type="checkbox"
          checked={!!user?.customer_agent_enabled}
          disabled={mutation.isPending}
          onChange={(e) => mutation.mutate(e.target.checked)}
        />
        Activar el agente inteligente
      </label>
      {user?.customer_agent_enabled && (
        <div className="space-y-2 rounded-lg bg-muted/50 p-3">
          <p className="text-xs text-muted-foreground">
            Atiende a clientes que ya tienen su tarjeta (entraron por su link o con su número). Los visitantes
            anónimos de tu página y la vista previa del widget hablan con el bot de siempre. Pruébalo como cliente
            de tu propio negocio, con tu teléfono:
          </p>
          <AgentTestButton />
        </div>
      )}
      {mutation.isError && <p className="text-sm text-red-600">{getApiError(mutation.error, 'No se pudo guardar')}</p>}
    </div>
  )
}
