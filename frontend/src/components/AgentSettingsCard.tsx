import { useMutation, useQueryClient } from '@tanstack/react-query'
import api, { getApiError } from '@/lib/api'
import { useAuth } from '@/contexts/AuthContext'
import { Sparkles } from 'lucide-react'

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
      {mutation.isError && <p className="text-sm text-red-600">{getApiError(mutation.error, 'No se pudo guardar')}</p>}
    </div>
  )
}
