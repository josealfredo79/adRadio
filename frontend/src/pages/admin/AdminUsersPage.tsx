import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import api from '@/lib/api'
import { formatDate } from '@/lib/utils'
import { Search, ChevronLeft, ChevronRight } from 'lucide-react'

interface AdminUser {
  id: string
  email: string
  role: string
  business_name: string | null
  business_category: string | null
  city: string | null
  phone: string | null
  whatsapp_number: string | null
  whatsapp_number_source: string
  subscription_status: string
  current_plan: string
  messages_remaining: number
  plan_expires_at: string | null
  stripe_customer_id: string | null
  created_at: string
}

interface UsersResponse {
  users: AdminUser[]
  total: number
  page: number
  per_page: number
}

const statusColors: Record<string, string> = {
  active: 'bg-green-100 text-green-700 dark:bg-green-900/50 dark:text-green-300',
  trial: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/50 dark:text-yellow-300',
  suspended: 'bg-red-100 text-red-700 dark:bg-red-900/50 dark:text-red-300',
  churned: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300',
}

const planColors: Record<string, string> = {
  starter: 'bg-blue-100 text-blue-700 dark:bg-blue-900/50 dark:text-blue-300',
  growth: 'bg-purple-100 text-purple-700 dark:bg-purple-900/50 dark:text-purple-300',
  pro: 'bg-orange-100 text-orange-700 dark:bg-orange-900/50 dark:text-orange-300',
  business: 'bg-red-100 text-red-700 dark:bg-red-900/50 dark:text-red-300',
  enterprise: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/50 dark:text-yellow-300',
}

export default function AdminUsersPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [search, setSearch] = useState(searchParams.get('search') || '')

  const page = Number(searchParams.get('page') || '1')
  const status = searchParams.get('status') || ''
  const plan = searchParams.get('plan') || ''
  const searchQuery = searchParams.get('search') || ''

  const { data, isLoading } = useQuery<UsersResponse>({
    queryKey: ['admin-users', page, status, plan, searchQuery],
    queryFn: () => {
      const params = new URLSearchParams({ page: String(page), per_page: '20' })
      if (status) params.set('status', status)
      if (plan) params.set('plan', plan)
      if (searchQuery) params.set('search', searchQuery)
      return api.get(`/admin/users?${params}`).then((r) => r.data)
    },
    staleTime: 1000 * 60,
  })

  const totalPages = data ? Math.ceil(data.total / data.per_page) : 1

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(searchParams)
    if (value) {
      next.set(key, value)
    } else {
      next.delete(key)
    }
    next.set('page', '1')
    setSearchParams(next)
  }

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault()
    setParam('search', search)
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Usuarios</h1>
          <p className="text-sm text-muted-foreground">{data?.total ?? 0} usuarios totales</p>
        </div>

        {/* Search */}
        <form onSubmit={handleSearch} className="flex gap-2">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Buscar por email o negocio..."
              className="pl-9 pr-4 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 w-64"
            />
          </div>
          <button type="submit" className="px-4 py-2 rounded-lg bg-brand-500 text-white text-sm font-medium hover:bg-brand-600 transition-colors">
            Buscar
          </button>
        </form>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => setParam('status', '')}
          className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${!status ? 'bg-brand-500 text-white' : 'bg-muted text-muted-foreground hover:bg-muted/80'}`}
        >
          Todos
        </button>
        {['trial', 'active', 'suspended', 'churned'].map((s) => (
          <button
            key={s}
            onClick={() => setParam('status', status === s ? '' : s)}
            className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${status === s ? 'bg-brand-500 text-white' : 'bg-muted text-muted-foreground hover:bg-muted/80'}`}
          >
            {s.charAt(0).toUpperCase() + s.slice(1)}
          </button>
        ))}

        <div className="w-px h-6 bg-border mx-1" />

        <button
          onClick={() => setParam('plan', '')}
          className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${!plan ? 'bg-brand-500 text-white' : 'bg-muted text-muted-foreground hover:bg-muted/80'}`}
        >
          Todos los planes
        </button>
        {['trial', 'starter', 'growth', 'pro', 'business', 'enterprise'].map((p) => (
          <button
            key={p}
            onClick={() => setParam('plan', plan === p ? '' : p)}
            className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${plan === p ? 'bg-brand-500 text-white' : 'bg-muted text-muted-foreground hover:bg-muted/80'}`}
          >
            {p.charAt(0).toUpperCase() + p.slice(1)}
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
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground hidden md:table-cell">Negocio</th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">Plan</th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">Estado</th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground hidden lg:table-cell">Mensajes</th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground hidden lg:table-cell">Registro</th>
                </tr>
              </thead>
              <tbody>
                {data.users.map((u) => (
                  <tr key={u.id} className="border-b border-border last:border-b-0 hover:bg-muted/30 transition-colors">
                    <td className="px-4 py-3">
                      <div className="font-medium text-foreground">{u.email}</div>
                      {u.role === 'admin' && (
                        <span className="text-xs text-purple-600 dark:text-purple-400">Admin</span>
                      )}
                    </td>
                    <td className="px-4 py-3 hidden md:table-cell">
                      <span className="text-foreground">{u.business_name || '—'}</span>
                      {u.city && <span className="text-muted-foreground ml-1">· {u.city}</span>}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${planColors[u.current_plan] || 'bg-gray-100 text-gray-700'}`}>
                        {u.current_plan.toUpperCase()}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${statusColors[u.subscription_status] || 'bg-gray-100 text-gray-700'}`}>
                        {u.subscription_status}
                      </span>
                    </td>
                    <td className="px-4 py-3 hidden lg:table-cell text-muted-foreground">
                      {u.messages_remaining}
                    </td>
                    <td className="px-4 py-3 hidden lg:table-cell text-muted-foreground">
                      {formatDate(u.created_at)}
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
                onClick={() => setParam('page', String(page - 1))}
                disabled={page <= 1}
                className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm border border-border disabled:opacity-50 hover:bg-muted transition-colors"
              >
                <ChevronLeft className="h-4 w-4" /> Anterior
              </button>
              <button
                onClick={() => setParam('page', String(page + 1))}
                disabled={page >= totalPages}
                className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm border border-border disabled:opacity-50 hover:bg-muted transition-colors"
              >
                Siguiente <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
