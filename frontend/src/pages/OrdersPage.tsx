import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api'
import { ShoppingBag, Search, CheckCircle, XCircle, Clock, ChevronDown } from 'lucide-react'
import PrintButton from '@/components/PrintButton'
import { formatDate } from '@/lib/utils'
import { cn } from '@/lib/utils'
import SEO from '@/components/SEO'

type OrderState = 'collecting_name' | 'collecting_address' | 'collecting_payment' | 'confirmed' | 'cancelled'

interface Order {
  id: string
  order_number: string
  state: OrderState
  items_raw: string | null
  customer_name: string | null
  customer_phone: string | null
  delivery_address: string | null
  payment_method: string | null
  confirmed_at: string | null
  created_at: string
}

const STATE_LABELS: Record<OrderState, string> = {
  collecting_name: 'Recabando nombre',
  collecting_address: 'Recabando dirección',
  collecting_payment: 'Recabando pago',
  confirmed: 'Confirmado',
  cancelled: 'Cancelado',
}

const STATE_COLORS: Record<OrderState, string> = {
  collecting_name: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/50 dark:text-yellow-300',
  collecting_address: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/50 dark:text-yellow-300',
  collecting_payment: 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-300',
  confirmed: 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300',
  cancelled: 'bg-muted text-muted-foreground',
}

const STATE_ICON: Record<OrderState, React.FC<{ className?: string }>> = {
  collecting_name: Clock,
  collecting_address: Clock,
  collecting_payment: Clock,
  confirmed: CheckCircle,
  cancelled: XCircle,
}

const FILTER_OPTIONS = [
  { value: '', label: 'Todos' },
  { value: 'confirmed', label: 'Confirmados' },
  { value: 'collecting_payment', label: 'Pendientes de pago' },
  { value: 'cancelled', label: 'Cancelados' },
]

export default function OrdersPage() {
  const qc = useQueryClient()
  const [search, setSearch] = useState('')
  const [stateFilter, setStateFilter] = useState('')
  const [expanded, setExpanded] = useState<string | null>(null)

  const { data, isLoading } = useQuery<{ total: number; items: Order[] }>({
    queryKey: ['orders', stateFilter],
    queryFn: () =>
      api.get('/orders', { params: stateFilter ? { state: stateFilter } : {} }).then((r) => r.data),
  })

  const patchState = useMutation({
    mutationFn: ({ id, state }: { id: string; state: string }) =>
      api.patch(`/orders/${id}/state`, { state }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['orders'] }),
  })

  const filtered = (data?.items ?? []).filter((o) => {
    const q = search.toLowerCase()
    return (
      !q ||
      (o.order_number ?? '').toLowerCase().includes(q) ||
      (o.customer_name ?? '').toLowerCase().includes(q) ||
      (o.customer_phone ?? '').includes(q) ||
      (o.items_raw ?? '').toLowerCase().includes(q)
    )
  })

  const confirmedCount = data?.items.filter((o) => o.state === 'confirmed').length ?? 0
  const pendingCount = data?.items.filter(
    (o) => !['confirmed', 'cancelled'].includes(o.state)
  ).length ?? 0

  return (
    <>
      <SEO title="Pedidos" description="Panel de control de IaRadio." noIndex />
      <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Pedidos</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Pedidos capturados por el bot de WhatsApp
          </p>
        </div>
        <PrintButton />
      </div>

      <div className="print-area">

      {/* Stats strip */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="rounded-xl border border-border bg-card p-5 shadow-sm">
          <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Total</p>
          <p className="mt-1 text-3xl font-bold text-foreground">{data?.total ?? 0}</p>
        </div>
        <div className="rounded-xl border border-green-100 bg-green-50 p-5 shadow-sm dark:border-green-950/50 dark:bg-green-950/30">
          <p className="text-xs font-medium uppercase tracking-wider text-green-600 dark:text-green-400">Confirmados</p>
          <p className="mt-1 text-3xl font-bold text-green-700 dark:text-green-300">{confirmedCount}</p>
        </div>
        <div className="rounded-xl border border-yellow-100 bg-yellow-50 p-5 shadow-sm dark:border-yellow-950/50 dark:bg-yellow-950/30">
          <p className="text-xs font-medium uppercase tracking-wider text-yellow-600 dark:text-yellow-400">En proceso</p>
          <p className="mt-1 text-3xl font-bold text-yellow-700 dark:text-yellow-300">{pendingCount}</p>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar por número, cliente, teléfono..."
            className="w-full rounded-lg border border-border py-2.5 pl-10 pr-4 text-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20"
          />
        </div>
        <div className="flex gap-2 flex-wrap">
          {FILTER_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => setStateFilter(opt.value)}
              className={cn(
                'rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                stateFilter === opt.value
                  ? 'bg-brand-500 text-white'
                  : 'border border-border text-muted-foreground hover:bg-muted'
              )}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {/* List */}
      <div className="rounded-xl border border-border bg-card shadow-sm overflow-hidden">
        {isLoading ? (
          <div className="space-y-3 p-6">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="h-16 rounded-lg bg-muted animate-pulse" />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
            <ShoppingBag className="h-12 w-12 mb-3" />
            <p className="text-sm">No hay pedidos todavía</p>
            <p className="text-xs mt-1">Los pedidos aparecerán cuando el bot los capture por WhatsApp</p>
          </div>
        ) : (
          <ul className="divide-y divide-border">
            {filtered.map((order) => {
              const Icon = STATE_ICON[order.state]
              const isOpen = expanded === order.id
              const isPending = !['confirmed', 'cancelled'].includes(order.state)
              return (
                <li key={order.id}>
                  {/* Row */}
                  <button
                    className="w-full flex items-center gap-4 px-6 py-4 text-left hover:bg-muted transition-colors"
                    onClick={() => setExpanded(isOpen ? null : order.id)}
                  >
                    <Icon
                      className={cn(
                        'h-5 w-5 shrink-0',
                        order.state === 'confirmed' ? 'text-green-500 dark:text-green-400' :
                        order.state === 'cancelled' ? 'text-muted-foreground' : 'text-yellow-500 dark:text-yellow-400'
                      )}
                    />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-semibold text-foreground text-sm">
                          #{order.order_number}
                        </span>
                        <span className={cn('rounded-full px-2 py-0.5 text-xs font-medium', STATE_COLORS[order.state])}>
                          {STATE_LABELS[order.state]}
                        </span>
                      </div>
                      <p className="mt-0.5 text-xs text-muted-foreground truncate">
                        {order.customer_name ?? '—'} · {order.customer_phone ?? '—'} · {formatDate(order.created_at)}
                      </p>
                    </div>
                    <ChevronDown
                      className={cn('h-4 w-4 text-muted-foreground shrink-0 transition-transform', isOpen && 'rotate-180')}
                    />
                  </button>

                  {/* Expanded detail */}
                  {isOpen && (
                    <div className="px-6 pb-5 bg-muted border-t border-border">
                      <dl className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
                        <div>
                          <dt className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Artículos</dt>
                          <dd className="mt-1 text-sm text-foreground whitespace-pre-wrap">{order.items_raw ?? '—'}</dd>
                        </div>
                        <div>
                          <dt className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Dirección</dt>
                          <dd className="mt-1 text-sm text-foreground">{order.delivery_address ?? '—'}</dd>
                        </div>
                        <div>
                          <dt className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Método de pago</dt>
                          <dd className="mt-1 text-sm text-foreground">{order.payment_method ?? '—'}</dd>
                        </div>
                        {order.confirmed_at && (
                          <div>
                            <dt className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Confirmado el</dt>
                            <dd className="mt-1 text-sm text-foreground">{formatDate(order.confirmed_at)}</dd>
                          </div>
                        )}
                      </dl>

                      {/* Actions */}
                      {isPending && (
                        <div className="mt-4 flex gap-2">
                          <button
                            onClick={() => patchState.mutate({ id: order.id, state: 'confirmed' })}
                            disabled={patchState.isPending}
                            className="flex items-center gap-1.5 rounded-lg bg-green-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-600 transition-colors disabled:opacity-50"
                          >
                            <CheckCircle className="h-3.5 w-3.5" />
                            Confirmar pedido
                          </button>
                          <button
                            onClick={() => patchState.mutate({ id: order.id, state: 'cancelled' })}
                            disabled={patchState.isPending}
                            className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-muted-foreground hover:bg-muted transition-colors disabled:opacity-50"
                          >
                            <XCircle className="h-3.5 w-3.5" />
                            Cancelar
                          </button>
                        </div>
                      )}
                    </div>
                  )}
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </div>
    </div>
    </>
  )
}
