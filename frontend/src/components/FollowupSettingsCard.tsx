import { useMutation, useQueryClient } from '@tanstack/react-query'
import api, { getApiError } from '@/lib/api'
import { useAuth } from '@/contexts/AuthContext'
import { BellRing } from 'lucide-react'

// Seguimiento automático — backend: services/followup_service.py. Encendido
// por defecto; el dueño lo puede apagar aquí.
export default function FollowupSettingsCard() {
  const { user, setUser } = useAuth()
  const qc = useQueryClient()
  const mutation = useMutation({
    mutationFn: (enabled: boolean) => api.patch('/me', { followup_enabled: enabled }).then((r) => r.data),
    onSuccess: (updated) => {
      setUser?.(updated)
      qc.invalidateQueries({ queryKey: ['me'] })
    },
  })

  return (
    <div className="rounded-xl bg-card p-6 shadow-sm border border-border space-y-3">
      <div className="flex items-center gap-2">
        <BellRing className="h-5 w-5 text-brand-500" />
        <h2 className="text-base font-semibold text-foreground">Seguimiento automático</h2>
      </div>
      <p className="text-sm text-muted-foreground">
        Si un cliente pregunta por un producto, un precio o una cita y no compra, tu asistente le escribe una sola
        vez al día siguiente para retomarlo ("¿Todavía te interesa? Te lo aparto"). Le llega por la web, gratis, o
        por WhatsApp si todavía está dentro de las 24 horas. Nunca de noche y máximo una vez por semana. A quien no
        se le puede escribir gratis te lo mostramos en tu resumen de las 8 am.
      </p>
      <label className="flex items-center gap-2 text-sm font-medium text-foreground">
        <input
          type="checkbox"
          checked={user?.followup_enabled !== false}
          disabled={mutation.isPending}
          onChange={(e) => mutation.mutate(e.target.checked)}
        />
        Darle seguimiento a los interesados
      </label>
      {mutation.isError && <p className="text-sm text-red-600">{getApiError(mutation.error, 'No se pudo guardar')}</p>}
    </div>
  )
}
