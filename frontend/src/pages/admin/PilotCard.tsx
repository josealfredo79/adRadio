import { useQuery } from '@tanstack/react-query'
import api from '@/lib/api'
import { isCold, lastSeen } from '@/pages/admin/pilotTime'

// Panel del piloto — backend: admin.pilot_overview (GET /admin/pilot). Sale de
// la base de IaRadio (decisión 2026-10-15: sin PostHog). Las cuentas admin no cuentan.

interface Funnel {
  registrados: number
  verificaron_correo: number
  en_prueba: number
  pagando: number
  abrieron_pago_sin_pagar: number
  cancelaron: number
  prueba_a_pago_pct: number
}

interface Week {
  semana: string
  registros: number
  verificaron: number
}

export interface PilotBusiness {
  id: string
  negocio: string
  email: string
  verificado: boolean
  estado: string
  plan: string
  alta: string
  ultimo_acceso: string | null
  prueba_vence: string | null
  chats_30d: number
  citas_30d: number
  pedidos_30d: number
  campanas_30d: number
  contactos: number
}

interface Pilot {
  embudo: Funnel
  semanas: Week[]
  negocios: PilotBusiness[]
}

const ESTADO: Record<string, string> = {
  trial: 'Prueba',
  active: 'Pagando',
  suspended: 'Suspendido',
  churned: 'Canceló',
}

function Tile({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <div className="rounded-lg border border-border bg-background p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-xl font-bold text-foreground tabular-nums">{value}</p>
      {hint && <p className="mt-0.5 text-[11px] text-muted-foreground">{hint}</p>}
    </div>
  )
}

export default function PilotCard() {
  const { data, isLoading, isError } = useQuery<Pilot>({
    queryKey: ['admin-pilot'],
    queryFn: () => api.get('/admin/pilot').then((r) => r.data),
    staleTime: 1000 * 60,
  })

  if (isLoading) return <div className="h-40 rounded-xl border border-border bg-card animate-pulse" />
  if (isError || !data) return <p className="text-sm text-red-600">No se pudo cargar el panel del piloto.</p>

  const f = data.embudo
  const maxWeek = Math.max(1, ...data.semanas.map((w) => w.registros))

  return (
    <section className="rounded-xl bg-card p-5 shadow-sm border border-border space-y-5">
      <div>
        <h2 className="text-lg font-semibold text-foreground">Piloto: cómo van los negocios</h2>
        <p className="text-sm text-muted-foreground">Sin contar cuentas de administrador.</p>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
        <Tile label="Registrados" value={f.registrados} />
        <Tile label="Verificaron correo" value={f.verificaron_correo} />
        <Tile label="En prueba" value={f.en_prueba} />
        <Tile label="Pagando" value={f.pagando} />
        <Tile label="Abrieron el pago" value={f.abrieron_pago_sin_pagar} hint="y no pagaron" />
        <Tile label="Cancelaron" value={f.cancelaron} />
        <Tile label="Prueba → pago" value={`${f.prueba_a_pago_pct}%`} hint="de los verificados" />
      </div>

      <div>
        <h3 className="mb-2 text-sm font-medium text-foreground">Altas por semana</h3>
        <ul className="space-y-1.5">
          {data.semanas.map((w) => (
            <li key={w.semana} className="flex items-center gap-3 text-xs">
              <span className="w-20 shrink-0 text-muted-foreground tabular-nums">
                {new Date(`${w.semana}T12:00:00`).toLocaleDateString('es-MX', { day: 'numeric', month: 'short' })}
              </span>
              <div className="h-3 flex-1 rounded bg-muted">
                <div className="h-3 rounded bg-brand-500" style={{ width: `${(w.registros / maxWeek) * 100}%` }} />
              </div>
              <span className="w-24 shrink-0 text-right text-foreground tabular-nums">
                {w.registros} ({w.verificaron} verif.)
              </span>
            </li>
          ))}
        </ul>
      </div>

      <div>
        <h3 className="mb-2 text-sm font-medium text-foreground">Negocios (uso de los últimos 30 días)</h3>
        {data.negocios.length === 0 ? (
          <p className="text-sm text-muted-foreground">Todavía no hay negocios registrados.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs text-muted-foreground">
                  <th className="py-2 pr-3 font-medium">Negocio</th>
                  <th className="py-2 pr-3 font-medium">Estado</th>
                  <th className="py-2 pr-3 font-medium">Último acceso</th>
                  <th className="py-2 pr-3 font-medium">Prueba vence</th>
                  <th className="py-2 pr-3 text-right font-medium">Chats</th>
                  <th className="py-2 pr-3 text-right font-medium">Citas</th>
                  <th className="py-2 pr-3 text-right font-medium">Pedidos</th>
                  <th className="py-2 pr-3 text-right font-medium">Campañas</th>
                  <th className="py-2 text-right font-medium">Contactos</th>
                </tr>
              </thead>
              <tbody>
                {data.negocios.map((n) => (
                  <tr key={n.id} className="border-b border-border/60 last:border-0">
                    <td className="py-2 pr-3">
                      <p className="font-medium text-foreground">{n.negocio}</p>
                      <p className="text-xs text-muted-foreground break-all">
                        {n.email}
                        {!n.verificado && ' · sin verificar'}
                      </p>
                    </td>
                    <td className="py-2 pr-3 text-foreground">{ESTADO[n.estado] ?? n.estado}</td>
                    <td className={`py-2 pr-3 ${isCold(n.ultimo_acceso) ? 'text-orange-600 dark:text-orange-400' : 'text-foreground'}`}>
                      {lastSeen(n.ultimo_acceso)}
                    </td>
                    <td className="py-2 pr-3 text-muted-foreground">
                      {n.prueba_vence ? new Date(n.prueba_vence).toLocaleDateString('es-MX', { day: 'numeric', month: 'short' }) : '—'}
                    </td>
                    <td className="py-2 pr-3 text-right tabular-nums">{n.chats_30d}</td>
                    <td className="py-2 pr-3 text-right tabular-nums">{n.citas_30d}</td>
                    <td className="py-2 pr-3 text-right tabular-nums">{n.pedidos_30d}</td>
                    <td className="py-2 pr-3 text-right tabular-nums">{n.campanas_30d}</td>
                    <td className="py-2 text-right tabular-nums">{n.contactos}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="mt-2 text-xs text-muted-foreground">En naranja: no ha entrado en más de 7 días.</p>
      </div>
    </section>
  )
}
