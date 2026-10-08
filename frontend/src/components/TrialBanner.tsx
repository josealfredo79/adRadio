import { NavLink } from 'react-router-dom'
import { useAuth } from '@/contexts/AuthContext'

// Prueba gratis: cuántos días quedan, los 5 de regalo y la pausa (backend:
// services/trial_lifecycle.py). Solo aparece cuando hay algo que decir.
export default function TrialBanner() {
  const { user } = useAuth()
  if (!user) return null

  if (user.paused) {
    return (
      <div className="mb-6 flex flex-col gap-3 rounded-xl border border-red-300 bg-red-50 p-4 sm:flex-row sm:items-center sm:justify-between dark:border-red-900 dark:bg-red-950/40">
        <div>
          <p className="font-semibold text-red-800 dark:text-red-200">Tu página y tu asistente están en pausa</p>
          <p className="text-sm text-red-700 dark:text-red-300">
            Terminó tu prueba gratis. No se borró nada: al activar un plan vuelve todo igual, al instante.
          </p>
        </div>
        <NavLink to="/app/plans" className="press shrink-0 rounded-lg bg-red-600 px-4 py-2 text-center text-sm font-semibold text-white hover:bg-red-700">
          Reactivar
        </NavLink>
      </div>
    )
  }

  const left = user.trial_days_left
  if (left == null || left > 5) return null
  const gift = Boolean(user.trial_extended_at)
  return (
    <div className="mb-6 flex flex-col gap-3 rounded-xl border border-amber-300 bg-amber-50 p-4 sm:flex-row sm:items-center sm:justify-between dark:border-amber-900 dark:bg-amber-950/40">
      <div>
        <p className="font-semibold text-amber-900 dark:text-amber-200">
          {gift
            ? '🎁 Vimos que tu página está funcionando: te regalamos 5 días más'
            : `Te ${left === 1 ? 'queda 1 día' : `quedan ${left} días`} de prueba gratis`}
        </p>
        <p className="text-sm text-amber-800 dark:text-amber-300">
          {gift
            ? `Te ${left === 1 ? 'queda 1 día' : `quedan ${left} días`}. Elige tu plan para que no se pause.`
            : 'Elige tu plan para que tu página y tu asistente sigan atendiendo.'}
        </p>
      </div>
      <NavLink to="/app/plans" className="press shrink-0 rounded-lg bg-amber-500 px-4 py-2 text-center text-sm font-semibold text-white hover:bg-amber-600">
        Ver planes
      </NavLink>
    </div>
  )
}
