import { useState } from 'react'
import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useAuth } from '@/contexts/AuthContext'
import { useTheme } from '@/contexts/ThemeContext'
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
  UserCog,
  MessageCircle,
  BarChart3,
  FileText,
  Bot,
  Moon,
  Sun,
  Shield,
  User,
  CreditCard as CreditCardIcon,
  FlaskConical,
  Kanban,
  Package,
} from 'lucide-react'
import { cn } from '@/lib/utils'

const navItems = [
  { to: '/app/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/app/campaigns', icon: Megaphone, label: 'Campañas' },
  { to: '/app/automations', icon: Bot, label: 'Automatizaciones' },
  { to: '/app/inbox', icon: MessageSquare, label: 'Inbox' },
  { to: '/app/orders', icon: ShoppingBag, label: 'Pedidos', badge: 'orders_pending' as const },
  { to: '/app/products', icon: Package, label: 'Catálogo' },
  { to: '/app/appointments', icon: CalendarDays, label: 'Citas' },
  { to: '/app/contacts', icon: Users, label: 'Contactos' },
  { to: '/app/pipeline', icon: Kanban, label: 'Pipeline' },
  { to: '/app/knowledge-base', icon: BookOpen, label: 'Base de conocimiento' },
  { to: '/app/lab', icon: FlaskConical, label: 'Laboratorio' },
  { to: '/app/team', icon: UserCog, label: 'Equipo' },
  { to: '/app/templates', icon: FileText, label: 'Plantillas' },
  { to: '/app/widget', icon: MessageCircle, label: 'Widget de chat' },
  { to: '/app/analytics', icon: BarChart3, label: 'Analytics' },
  { to: '/app/plans', icon: CreditCard, label: 'Planes' },
  { to: '/app/settings', icon: Settings, label: 'Configuración' },
]

const adminNavItems = [
  { to: '/app/admin', icon: LayoutDashboard, label: 'Panel Admin' },
  { to: '/app/admin/users', icon: User, label: 'Usuarios' },
  { to: '/app/admin/subscriptions', icon: CreditCardIcon, label: 'Suscripciones' },
]

export default function Layout() {
  const { user, logout } = useAuth()
  const { toggle: toggleTheme } = useTheme()
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
      <div className="flex items-center gap-2 px-6 py-5 border-b border-border">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-500">
          <Radio className="h-4 w-4 text-white" />
        </div>
        <span className="text-xl font-bold text-foreground">IaRadio</span>
      </div>

      {/* Plan badge + theme toggle */}
      <div className="flex items-center justify-between px-6 py-3">
        <span className={cn(
          'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium',
          user?.subscription_status === 'active'
            ? 'bg-green-100 text-green-700 dark:bg-green-900/50 dark:text-green-300'
            : 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/50 dark:text-yellow-300'
        )}>
          {user?.current_plan?.toUpperCase() ?? 'TRIAL'} · {user?.messages_remaining ?? 0} msgs
        </span>
        <button
          onClick={toggleTheme}
          className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
          aria-label="Cambiar tema"
        >
          <Sun className="h-4 w-4 dark:hidden" />
          <Moon className="hidden h-4 w-4 dark:block" />
        </button>
      </div>

      {/* Navigation (scrollable so every item + logout stays reachable on short screens) */}
      <div className="flex-1 min-h-0 overflow-y-auto">
      <nav className="px-3 py-2 space-y-1">
        {navItems.map(({ to, icon: Icon, label, badge }) => {
          const count = badge === 'orders_pending' ? (dashData?.orders_pending ?? 0) : 0
          return (
            <NavLink
              key={to}
              to={to}
              onClick={() => setSidebarOpen(false)}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-3 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-brand-50 text-brand-600 dark:bg-brand-500/10 dark:text-brand-400'
                    : 'text-muted-foreground hover:bg-muted hover:text-foreground'
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

      {/* Admin section (visible only to admins) */}
      {user?.role === 'admin' && (
        <>
          <div className="px-6 pt-4 pb-1">
            <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              <Shield className="h-3 w-3" />
              Administración
            </div>
          </div>
          <nav className="px-3 pb-2 space-y-1">
            {adminNavItems.map(({ to, icon: Icon, label }) => (
              <NavLink
                key={to}
                to={to}
                onClick={() => setSidebarOpen(false)}
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-3 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors',
                    isActive
                      ? 'bg-purple-100 text-purple-700 dark:bg-purple-500/10 dark:text-purple-400'
                      : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                  )
                }
              >
                <Icon className="h-4 w-4 shrink-0" />
                <span className="flex-1">{label}</span>
              </NavLink>
            ))}
          </nav>
        </>
      )}
      </div>

      {/* User + logout */}
      <div className="border-t border-border p-4">
        <div className="mb-3">
          <p className="text-sm font-medium text-foreground truncate">{user?.business_name ?? user?.email}</p>
          <p className="text-xs text-muted-foreground truncate">{user?.email}</p>
        </div>
        <button
          onClick={handleLogout}
          className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-muted-foreground hover:bg-muted hover:text-red-600 transition-colors"
        >
          <LogOut className="h-4 w-4" />
          Cerrar sesión
        </button>
      </div>
    </>
  )

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-20 bg-black/40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside className={cn(
        'fixed inset-y-0 left-0 z-30 flex w-64 flex-col bg-card border-r border-border shadow-sm transition-transform duration-200 lg:static lg:translate-x-0',
        sidebarOpen ? 'translate-x-0' : '-translate-x-full'
      )}>
        {/* Mobile close button */}
        <button
          onClick={() => setSidebarOpen(false)}
          className="absolute right-3 top-4 rounded-lg p-1.5 text-muted-foreground hover:bg-muted lg:hidden"
        >
          <X className="h-4 w-4" />
        </button>
        {sidebarContent}
      </aside>

      {/* Main content */}
      <main className="flex flex-1 flex-col overflow-hidden">
        {/* Mobile topbar */}
        <div className="flex items-center gap-3 border-b border-border bg-card px-4 py-3 lg:hidden">
          <button
            onClick={() => setSidebarOpen(true)}
            className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted"
          >
            <Menu className="h-5 w-5" />
          </button>
          <div className="flex items-center gap-2">
            <div className="flex h-6 w-6 items-center justify-center rounded-md bg-brand-500">
              <Radio className="h-3.5 w-3.5 text-white" />
            </div>
            <span className="font-bold text-foreground">IaRadio</span>
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
