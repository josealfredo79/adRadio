import { useState } from 'react'
import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useAuth } from '@/contexts/AuthContext'
import api from '@/lib/api'
import {
  LayoutDashboard,
  Users,
  Megaphone,
  MessageSquare,
  BookOpen,
  CreditCard,
  LogOut,
  Radio,
  Settings,
  ShoppingBag,
  CalendarDays,
  Menu,
  X,
} from 'lucide-react'
import { cn } from '@/lib/utils'

const navItems = [
  { to: '/app/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/app/campaigns', icon: Megaphone, label: 'Campañas' },
  { to: '/app/inbox', icon: MessageSquare, label: 'Inbox' },
  { to: '/app/orders', icon: ShoppingBag, label: 'Pedidos', badge: 'orders_pending' as const },
  { to: '/app/appointments', icon: CalendarDays, label: 'Citas' },
  { to: '/app/contacts', icon: Users, label: 'Contactos' },
  { to: '/app/knowledge-base', icon: BookOpen, label: 'Base de conocimiento' },
  { to: '/app/plans', icon: CreditCard, label: 'Planes' },
  { to: '/app/settings', icon: Settings, label: 'Configuración' },
]

export default function Layout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [sidebarOpen, setSidebarOpen] = useState(false)

  const { data: dashData } = useQuery<{ orders_pending: number }>({
    queryKey: ['dashboard'],
    queryFn: () => api.get('/dashboard').then((r) => r.data),
    staleTime: 1000 * 60 * 2,
  })

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }

  const sidebarContent = (
    <>
      {/* Logo */}
      <div className="flex items-center gap-2 px-6 py-5 border-b border-gray-100">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-500">
          <Radio className="h-4 w-4 text-white" />
        </div>
        <span className="text-xl font-bold text-gray-900">IaRadio</span>
      </div>

      {/* Plan badge */}
      <div className="px-6 py-3">
        <span className={cn(
          'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium',
          user?.subscription_status === 'active'
            ? 'bg-green-100 text-green-700'
            : 'bg-yellow-100 text-yellow-700'
        )}>
          {user?.current_plan?.toUpperCase() ?? 'TRIAL'} · {user?.messages_remaining ?? 0} msgs
        </span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-2 space-y-1">
        {navItems.map(({ to, icon: Icon, label, badge }) => {
          const count = badge === 'orders_pending' ? (dashData?.orders_pending ?? 0) : 0
          return (
            <NavLink
              key={to}
              to={to}
              onClick={() => setSidebarOpen(false)}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-brand-50 text-brand-600'
                    : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
                )
              }
            >
              <Icon className="h-4 w-4 shrink-0" />
              <span className="flex-1">{label}</span>
              {count > 0 && (
                <span className="flex h-5 min-w-5 items-center justify-center rounded-full bg-red-500 px-1.5 text-[10px] font-bold text-white">
                  {count > 99 ? '99+' : count}
                </span>
              )}
            </NavLink>
          )
        })}
      </nav>

      {/* User + logout */}
      <div className="border-t border-gray-100 p-4">
        <div className="mb-3">
          <p className="text-sm font-medium text-gray-900 truncate">{user?.business_name ?? user?.email}</p>
          <p className="text-xs text-gray-500 truncate">{user?.email}</p>
        </div>
        <button
          onClick={handleLogout}
          className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-gray-600 hover:bg-gray-50 hover:text-red-600 transition-colors"
        >
          <LogOut className="h-4 w-4" />
          Cerrar sesión
        </button>
      </div>
    </>
  )

  return (
    <div className="flex h-screen overflow-hidden bg-gray-50">
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-20 bg-black/40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside className={cn(
        'fixed inset-y-0 left-0 z-30 flex w-64 flex-col bg-white border-r border-gray-200 shadow-sm transition-transform duration-200 lg:static lg:translate-x-0',
        sidebarOpen ? 'translate-x-0' : '-translate-x-full'
      )}>
        {/* Mobile close button */}
        <button
          onClick={() => setSidebarOpen(false)}
          className="absolute right-3 top-4 rounded-lg p-1.5 text-gray-400 hover:bg-gray-100 lg:hidden"
        >
          <X className="h-4 w-4" />
        </button>
        {sidebarContent}
      </aside>

      {/* Main content */}
      <main className="flex flex-1 flex-col overflow-hidden">
        {/* Mobile topbar */}
        <div className="flex items-center gap-3 border-b border-gray-200 bg-white px-4 py-3 lg:hidden">
          <button
            onClick={() => setSidebarOpen(true)}
            className="rounded-lg p-1.5 text-gray-600 hover:bg-gray-100"
          >
            <Menu className="h-5 w-5" />
          </button>
          <div className="flex items-center gap-2">
            <div className="flex h-6 w-6 items-center justify-center rounded-md bg-brand-500">
              <Radio className="h-3.5 w-3.5 text-white" />
            </div>
            <span className="font-bold text-gray-900">IaRadio</span>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 sm:py-8">
            <Outlet />
          </div>
        </div>
      </main>
    </div>
  )
}
