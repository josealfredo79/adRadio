import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from '@/contexts/AuthContext'
import { Suspense, lazy } from 'react'

const LandingPage = lazy(() => import('@/pages/LandingPage'))
const LoginPage = lazy(() => import('@/pages/LoginPage'))
const RegisterPage = lazy(() => import('@/pages/RegisterPage'))
const VerifyEmailPage = lazy(() => import('@/pages/VerifyEmailPage'))
const DashboardPage = lazy(() => import('@/pages/DashboardPage'))
const ContactsPage = lazy(() => import('@/pages/ContactsPage'))
const CampaignsPage = lazy(() => import('@/pages/CampaignsPage'))
const KnowledgeBasePage = lazy(() => import('@/pages/KnowledgeBasePage'))
const PlansPage = lazy(() => import('@/pages/PlansPage'))
const SettingsPage = lazy(() => import('@/pages/SettingsPage'))
const Layout = lazy(() => import('@/components/Layout'))
const ForgotPasswordPage = lazy(() => import('@/pages/ForgotPasswordPage'))
const ResetPasswordPage = lazy(() => import('@/pages/ResetPasswordPage'))
const InboxPage = lazy(() => import('@/pages/InboxPage'))
const OrdersPage = lazy(() => import('@/pages/OrdersPage'))
const AppointmentsPage = lazy(() => import('@/pages/AppointmentsPage'))
const TermsPage = lazy(() => import('@/pages/TermsPage'))
const PrivacyPage = lazy(() => import('@/pages/PrivacyPage'))
const CustomerStoriesPage = lazy(() => import('@/pages/CustomerStoriesPage'))
const TeamPage = lazy(() => import('@/pages/TeamPage'))
const WidgetPage = lazy(() => import('@/pages/WidgetPage'))
const AnalyticsPage = lazy(() => import('@/pages/AnalyticsPage'))
const AutomationsPage = lazy(() => import('@/pages/AutomationsPage'))
const TemplatesPage = lazy(() => import('@/pages/TemplatesPage'))
const LabPage = lazy(() => import('@/pages/LabPage'))
const PipelinePage = lazy(() => import('@/pages/PipelinePage'))
const NotFoundPage = lazy(() => import('@/pages/NotFoundPage'))
const AdminRoute = lazy(() => import('@/components/AdminRoute'))
const AdminDashboardPage = lazy(() => import('@/pages/admin/AdminDashboardPage'))
const AdminUsersPage = lazy(() => import('@/pages/admin/AdminUsersPage'))
const AdminSubscriptionsPage = lazy(() => import('@/pages/admin/AdminSubscriptionsPage'))

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return <div className="flex h-screen items-center justify-center">Cargando...</div>
  return user ? <>{children}</> : <Navigate to="/login" replace />
}

function PublicRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return null
  if (!user) return <>{children}</>
  return <Navigate to={user.role === 'admin' ? '/app/admin' : '/app/dashboard'} replace />
}

function RoleRedirect() {
  const { user } = useAuth()
  return <Navigate to={user?.role === 'admin' ? '/app/admin' : '/app/dashboard'} replace />
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Suspense fallback={<div className="flex h-screen items-center justify-center text-brand-500">Cargando...</div>}>
          <Routes>
            {/* Landing */}
            <Route path="/" element={<LandingPage />} />
            <Route path="/terms" element={<TermsPage />} />
            <Route path="/privacy" element={<PrivacyPage />} />
            <Route path="/customer-stories" element={<CustomerStoriesPage />} />

            {/* Public */}
            <Route path="/login" element={<PublicRoute><LoginPage /></PublicRoute>} />
            <Route path="/register" element={<PublicRoute><RegisterPage /></PublicRoute>} />
            <Route path="/verify-email" element={<VerifyEmailPage />} />
            <Route path="/forgot-password" element={<PublicRoute><ForgotPasswordPage /></PublicRoute>} />
            <Route path="/reset-password" element={<ResetPasswordPage />} />

            {/* Private */}
            <Route path="/app" element={<PrivateRoute><Layout /></PrivateRoute>}>
              <Route index element={<RoleRedirect />} />
              <Route path="dashboard" element={<DashboardPage />} />
              <Route path="contacts" element={<ContactsPage />} />
              <Route path="pipeline" element={<PipelinePage />} />
              <Route path="campaigns" element={<CampaignsPage />} />
              <Route path="inbox" element={<InboxPage />} />
              <Route path="orders" element={<OrdersPage />} />
              <Route path="appointments" element={<AppointmentsPage />} />
              <Route path="knowledge-base" element={<KnowledgeBasePage />} />
              <Route path="lab" element={<LabPage />} />
              <Route path="plans" element={<PlansPage />} />
              <Route path="analytics" element={<AnalyticsPage />} />
              <Route path="automations" element={<AutomationsPage />} />
              <Route path="templates" element={<TemplatesPage />} />
              <Route path="settings" element={<SettingsPage />} />
              <Route path="team" element={<TeamPage />} />
              <Route path="widget" element={<WidgetPage />} />

              {/* Admin routes */}
              <Route path="admin" element={<AdminRoute><AdminDashboardPage /></AdminRoute>} />
              <Route path="admin/users" element={<AdminRoute><AdminUsersPage /></AdminRoute>} />
              <Route path="admin/subscriptions" element={<AdminRoute><AdminSubscriptionsPage /></AdminRoute>} />

              <Route path="*" element={<NotFoundPage />} />
            </Route>

            <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </Suspense>
      </BrowserRouter>
    </AuthProvider>
  )
}
