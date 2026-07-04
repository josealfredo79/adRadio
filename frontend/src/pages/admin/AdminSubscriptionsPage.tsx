import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api'
import { formatDate, formatCurrency } from '@/lib/utils'
import { Search, ChevronLeft, ChevronRight, Edit2, X, Save } from 'lucide-react'

interface SubscriptionUser {
  id: string
  email: string
  business_name: string | null
  subscription_status: string
  current_plan: string
  messages_remaining: number
  plan_expires_at: string | null
  cancel_at_period_end: boolean
  stripe_customer_id: string | null
  created_at: string
}

interface SubscriptionsResponse {
  users: SubscriptionUser[]
  total: number
  page: number
  per_page: number
}

interface Transaction {
  id: string
  amount: number
  currency: string
  plan: string | null
  status: string
  invoice_pdf_url: string | null
  created_at: string
}

const statusColors: Record<string, string> = {
  active: 'bg-green-100 text-green-700 dark:bg-green-900/50 dark:text-green-300',
  trial: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/50 dark:text-yellow-300',
  suspended: 'bg-red-100 text-red-700 dark:bg-red-900/50 dark:text-red-300',
  churned: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300',
}

export default function AdminSubscriptionsPage() {
  const qc = useQueryClient()
  const [page, setPage] = useState(1)
  const [statusFilter, setStatusFilter] = useState('')
  const [editingUser, setEditingUser] = useState<SubscriptionUser | null>(null)
  const [editForm, setEditForm] = useState({ current_plan: '', subscription_status: '', messages_remaining: 0 })

  const { data, isLoading } = useQuery<SubscriptionsResponse>({
    queryKey: ['admin-subscriptions', page, statusFilter],
    queryFn: () => {
      const params = new URLSearchParams({ page: String(page), per_page: '20' })
      if (statusFilter) params.set('status', statusFilter)
      return api.get(`/admin/subscriptions?${params}`).then((r) => r.data)
    },
    staleTime: 1000 * 60,
  })

  const updateMutation = useMutation({
    mutationFn: (body: { current_plan?: string; subscription_status?: string; messages_remaining?: number }) =>
      api.patch(`/admin/subscriptions/${editingUser?.id}`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin-subscriptions'] })
      setEditingUser(null)
    },
  })

  const totalPages = data ? Math.ceil(data.total / data.per_page) : 1

  const startEdit = (user: SubscriptionUser) => {
    setEditingUser(user)
    setEditForm({
      current_plan: user.current_plan,
      subscription_status: user.subscription_status,
      messages_remaining: user.messages_remaining,
    })
  }

  const saveEdit = () => {
    updateMutation.mutate(editForm)
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Suscripciones</h1>
        <p className="text-sm text-muted-foreground">Gestiona planes y estados de suscripción</p>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => { setStatusFilter(''); setPage(1) }}
          className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${!statusFilter ? 'bg-brand-500 text-white' : 'bg-muted text-muted-foreground hover:bg-muted/80'}`}
        >
          Todos
        </button>
        {['trial', 'active', 'suspended', 'churned'].map((s) => (
          <button
            key={s}
            onClick={() => { setStatusFilter(statusFilter === s ? '' : s); setPage(1) }}
            className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${statusFilter === s ? 'bg-brand-500 text-white' : 'bg-muted text-muted-foreground hover:bg-muted/80'}`}
          >
            {s.charAt(0).toUpperCase() + s.slice(1)}
          </button>
        ))}
      </div>

      {/* Table */}
      <div className="rounded-xl border border-border bg-card shadow-sm overflow-hidden">
        {isLoading ? (
          <div className="p-8 text-center text-muted-foreground">Cargando...</div>
        ) : !data?.users.length ? (
          <div className="p-8 text-center text-muted-foreground">No se encontraron usuarios</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/50">
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">Usuario</th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">Plan</th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">Estado</th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground hidden md:table-cell">Mensajes</th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground hidden lg:table-cell">Expira</th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">Acciones</th>
                </tr>
              </thead>
              <tbody>
                {data.users.map((u) => (
                  <tr key={u.id} className="border-b border-border last:border-b-0 hover:bg-muted/30 transition-colors">
                    <td className="px-4 py-3">
                      <div className="font-medium text-foreground">{u.email}</div>
                      <div className="text-xs text-muted-foreground">{u.business_name || 'Sin negocio'}</div>
                    </td>
                    <td className="px-4 py-3">
                      <span className="inline-flex rounded-full px-2 py-0.5 text-xs font-medium bg-brand-100 text-brand-700 dark:bg-brand-900/50 dark:text-brand-300">
                        {u.current_plan.toUpperCase()}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${statusColors[u.subscription_status] || 'bg-gray-100 text-gray-700'}`}>
                        {u.subscription_status}
                      </span>
                    </td>
                    <td className="px-4 py-3 hidden md:table-cell text-muted-foreground">
                      {u.messages_remaining}
                    </td>
                    <td className="px-4 py-3 hidden lg:table-cell text-muted-foreground">
                      {u.plan_expires_at ? formatDate(u.plan_expires_at) : '—'}
                    </td>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => startEdit(u)}
                        className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
                      >
                        <Edit2 className="h-4 w-4" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination */}
        {data && data.total > data.per_page && (
          <div className="flex items-center justify-between border-t border-border px-4 py-3">
            <span className="text-sm text-muted-foreground">
              Página {data.page} de {totalPages}
            </span>
            <div className="flex gap-2">
              <button
                onClick={() => setPage(Math.max(1, page - 1))}
                disabled={page <= 1}
                className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm border border-border disabled:opacity-50 hover:bg-muted transition-colors"
              >
                <ChevronLeft className="h-4 w-4" /> Anterior
              </button>
              <button
                onClick={() => setPage(Math.min(totalPages, page + 1))}
                disabled={page >= totalPages}
                className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm border border-border disabled:opacity-50 hover:bg-muted transition-colors"
              >
                Siguiente <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Edit modal */}
      {editingUser && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="rounded-2xl bg-card p-6 shadow-2xl w-full max-w-md mx-4">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-bold text-foreground">Editar Suscripción</h2>
              <button onClick={() => setEditingUser(null)} className="p-1 rounded-lg hover:bg-muted">
                <X className="h-5 w-5" />
              </button>
            </div>
            <p className="text-sm text-muted-foreground mb-4">{editingUser.email}</p>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Plan</label>
                <select
                  value={editForm.current_plan}
                  onChange={(e) => setEditForm({ ...editForm, current_plan: e.target.value })}
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
                >
                  {['trial', 'starter', 'growth', 'pro', 'business', 'enterprise'].map((p) => (
                    <option key={p} value={p}>{p.charAt(0).toUpperCase() + p.slice(1)}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Estado</label>
                <select
                  value={editForm.subscription_status}
                  onChange={(e) => setEditForm({ ...editForm, subscription_status: e.target.value })}
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
                >
                  {['trial', 'active', 'suspended', 'churned'].map((s) => (
                    <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Mensajes restantes</label>
                <input
                  type="number"
                  value={editForm.messages_remaining}
                  onChange={(e) => setEditForm({ ...editForm, messages_remaining: Number(e.target.value) })}
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
                />
              </div>
            </div>

            <div className="flex justify-end gap-2 mt-6">
              <button
                onClick={() => setEditingUser(null)}
                className="px-4 py-2 rounded-lg text-sm border border-border hover:bg-muted transition-colors"
              >
                Cancelar
              </button>
              <button
                onClick={saveEdit}
                disabled={updateMutation.isPending}
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm bg-brand-500 text-white hover:bg-brand-600 disabled:opacity-50 transition-colors"
              >
                <Save className="h-4 w-4" />
                {updateMutation.isPending ? 'Guardando...' : 'Guardar'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
