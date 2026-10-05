import { useMutation, useQueryClient } from '@tanstack/react-query'
import api, { getApiError } from '@/lib/api'
import { useAuth } from '@/contexts/AuthContext'
import { Compass } from 'lucide-react'

// "Descubre negocios" de /mi: los clientes de otros negocios IaRadio te
// encuentran y te escriben gratis. Encendido por defecto; aquí se apaga.
export default function DirectoryCard() {
  const { user, setUser } = useAuth()
  const qc = useQueryClient()
  const mutation = useMutation({
    mutationFn: (listed: boolean) => api.patch('/me', { directory_listed: listed }).then((r) => r.data),
    onSuccess: (updated) => {
      setUser?.(updated)
      qc.invalidateQueries({ queryKey: ['me'] })
    },
  })
  const listed = user?.directory_listed ?? true

  return (
    <div className="rounded-xl bg-card p-6 shadow-sm border border-border space-y-3">
      <div className="flex items-center gap-2">
        <Compass className="h-5 w-5 text-brand-500" />
        <h2 className="text-base font-semibold text-foreground">Directorio de IaRadio</h2>
      </div>
      <p className="text-sm text-muted-foreground">
        Los clientes de otros negocios IaRadio te encuentran en "Descubre negocios", se unen y te escriben gratis, sin
        WhatsApp. Llegan a tus Contactos y a tu Inbox como cualquier cliente.
        {!user?.slug && ' Para aparecer, primero elige el link de tu página en Widget de chat.'}
      </p>
      <label className="flex items-center gap-2 text-sm font-medium text-foreground">
        <input
          type="checkbox"
          checked={listed}
          disabled={mutation.isPending}
          onChange={(e) => mutation.mutate(e.target.checked)}
        />
        Aparecer en el directorio
      </label>
      {mutation.isError && <p className="text-sm text-red-600">{getApiError(mutation.error, 'No se pudo guardar')}</p>}
    </div>
  )
}
