import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import api from '@/lib/api'
import { formatNumber, formatCurrency } from '@/lib/utils'
import {
  Users,
  TrendingUp,
  MessageSquare,
  DollarSign,
  UserPlus,
  CreditCard,
  AlertTriangle,
  UserX,
} from 'lucide-react'

interface AdminStats {
  total_users: number
  users_trial: number
  users_active: number
  users_suspended: number
  users_churned: number
  mrr_mxn: number
  mrr_usd: number
  messages_sent_today: number
  messages_sent_month: number
  new_users_this_month: number
  stripe_connected: number
}

function StatCard({ label, value, icon: Icon, color, onClick }: {
  label: string
  value: string | number
  icon: React.ElementType
  color: string
  onClick?: () => void
}) {
  return (
    <div
      onClick={onClick}
      className={`rounded-xl bg-card p-5 shadow-sm border border-border ${onClick ? 'cursor-pointer hover:shadow-md transition-shadow' : ''}`}
    >
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-muted-foreground">{label}</p>
          <p className="mt-1 text-2xl font-bold text-foreground">{value}</p>
        </div>
        <div className={`rounded-lg p-3 ${color}`}>
          <Icon className="h-5 w-5 text-white" />
        </div>
      </div>
    </div>
  )
}

export default function AdminDashboardPage() {
  const navigate = useNavigate()
  const { data: stats, isLoading } = useQuery<AdminStats>({
    queryKey: ['admin-stats'],
    queryFn: () => api.get('/admin/stats').then((r) => r.data),
    staleTime: 1000 * 60,
  })

  if (isLoading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-foreground">Panel de Administración</h1>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {[...Array(8)].map((_, i) => (
            <div key={i} className="rounded-xl bg-card p-5 shadow-sm border border-border animate-pulse">
              <div className="h-4 bg-muted rounded w-24 mb-3" />
              <div className="h-8 bg-muted rounded w-16" />
            </div>
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-foreground">Panel de Administración</h1>

      {/* User metrics */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Total Usuarios"
          value={formatNumber(stats?.total_users ?? 0)}
          icon={Users}
          color="bg-blue-500"
          onClick={() => navigate('/app/admin/users')}
        />
        <StatCard
          label="Activos"
          value={formatNumber(stats?.users_active ?? 0)}
          icon={TrendingUp}
          color="bg-green-500"
          onClick={() => navigate('/app/admin/users?status=active')}
        />
        <StatCard
          label="Trial"
          value={formatNumber(stats?.users_trial ?? 0)}
          icon={UserPlus}
          color="bg-yellow-500"
          onClick={() => navigate('/app/admin/users?status=trial')}
        />
        <StatCard
          label="Churned"
          value={formatNumber(stats?.users_churned ?? 0)}
          icon={UserX}
          color="bg-red-500"
          onClick={() => navigate('/app/admin/users?status=churned')}
        />
      </div>

      {/* Revenue + Messages */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="MRR (MXN)"
          value={formatCurrency(stats?.mrr_mxn ?? 0, 'MXN')}
          icon={DollarSign}
          color="bg-emerald-500"
        />
        <StatCard
          label="MRR (USD)"
          value={formatCurrency(stats?.mrr_usd ?? 0, 'USD')}
          icon={DollarSign}
          color="bg-teal-500"
        />
        <StatCard
          label="Mensajes Hoy"
          value={formatNumber(stats?.messages_sent_today ?? 0)}
          icon={MessageSquare}
          color="bg-indigo-500"
        />
        <StatCard
          label="Mensajes Mes"
          value={formatNumber(stats?.messages_sent_month ?? 0)}
          icon={MessageSquare}
          color="bg-violet-500"
        />
      </div>

      {/* Secondary metrics */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatCard
          label="Nuevos Este Mes"
          value={formatNumber(stats?.new_users_this_month ?? 0)}
          icon={UserPlus}
          color="bg-cyan-500"
        />
        <StatCard
          label="Suspendidos"
          value={formatNumber(stats?.users_suspended ?? 0)}
          icon={AlertTriangle}
          color="bg-orange-500"
          onClick={() => navigate('/app/admin/users?status=suspended')}
        />
        <StatCard
          label="Stripe Conectados"
          value={formatNumber(stats?.stripe_connected ?? 0)}
          icon={CreditCard}
          color="bg-pink-500"
        />
      </div>
    </div>
  )
}
