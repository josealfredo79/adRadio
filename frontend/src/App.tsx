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

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return <div className="flex h-screen items-center justify-center">Cargando...</div>
  return user ? <>{children}</> : <Navigate to="/login" replace />
}

function PublicRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return null
  return user ? <Navigate to="/app/dashboard" replace /> : <>{children}</>
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Suspense fallback={<div className="flex h-screen items-center justify-center text-brand-500">Cargando...</div>}>
          <Routes>
            {/* Landing */}
            <Route path="/" element={<LandingPage />} />

            {/* Public */}
            <Route path="/login" element={<PublicRoute><LoginPage /></PublicRoute>} />
            <Route path="/register" element={<PublicRoute><RegisterPage /></PublicRoute>} />
            <Route path="/verify-email" element={<VerifyEmailPage />} />
            <Route path="/forgot-password" element={<PublicRoute><ForgotPasswordPage /></PublicRoute>} />
            <Route path="/reset-password" element={<ResetPasswordPage />} />

            {/* Private */}
            <Route path="/app" element={<PrivateRoute><Layout /></PrivateRoute>}>
              <Route index element={<Navigate to="/app/dashboard" replace />} />
              <Route path="dashboard" element={<DashboardPage />} />
              <Route path="contacts" element={<ContactsPage />} />
              <Route path="campaigns" element={<CampaignsPage />} />
              <Route path="inbox" element={<InboxPage />} />
              <Route path="orders" element={<OrdersPage />} />
              <Route path="appointments" element={<AppointmentsPage />} />
              <Route path="knowledge-base" element={<KnowledgeBasePage />} />
              <Route path="plans" element={<PlansPage />} />
              <Route path="settings" element={<SettingsPage />} />
            </Route>

            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </BrowserRouter>
    </AuthProvider>
  )
}
