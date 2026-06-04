import { useState } from 'react'
import { Link } from 'react-router-dom'
import api from '@/lib/api'
import { Radio, ArrowLeft, CheckCircle } from 'lucide-react'
import SEO from '@/components/SEO'

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [loading, setLoading] = useState(false)
  const [sent, setSent] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await api.post('/auth/forgot-password', { email })
      setSent(true)
    } catch {
      setError('Error al enviar el correo. Intenta de nuevo.')
    } finally {
      setLoading(false)
    }
  }

  if (sent) {
    return (
      <>
        <SEO title="Revisa tu correo" noIndex />
        <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-brand-50 to-indigo-100 px-4 dark:from-gray-950 dark:to-gray-900">
        <div className="w-full max-w-md rounded-2xl bg-white p-10 text-center shadow-xl dark:bg-gray-950 dark:border dark:border-gray-800">
          <CheckCircle className="mx-auto mb-4 h-14 w-14 text-green-500" />
          <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100">Revisa tu correo</h2>
          <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
            Si el email existe en nuestra base de datos, recibirás un enlace para restablecer tu contraseña.
          </p>
          <Link
            to="/login"
            className="mt-6 inline-flex items-center gap-2 text-sm text-brand-600 hover:underline dark:text-brand-400"
          >
            <ArrowLeft className="h-4 w-4" />
            Volver al login
          </Link>
        </div>
      </div>
    </>
  )
  }

  return (
    <>
      <SEO title="Recuperar contraseña" description="Recupera el acceso a tu cuenta de IaRadio." noIndex />
      <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-brand-50 to-indigo-100 px-4 dark:from-gray-950 dark:to-gray-900">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-500 shadow-lg">
            <Radio className="h-7 w-7 text-white" />
          </div>
          <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100">IaRadio</h1>
        </div>

        <div className="rounded-2xl bg-white p-8 shadow-xl dark:bg-gray-950 dark:border dark:border-gray-800">
          <h2 className="mb-2 text-xl font-semibold text-gray-900 dark:text-gray-100">Recuperar contraseña</h2>
          <p className="mb-6 text-sm text-gray-500 dark:text-gray-400">
            Ingresa tu email y te enviaremos un enlace para restablecer tu contraseña.
          </p>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">Email</label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded-lg border border-gray-300 bg-white px-3.5 py-2.5 text-sm text-gray-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100 dark:placeholder-gray-500"
                placeholder="tu@negocio.com"
              />
            </div>

            {error && (
              <p className="rounded-lg bg-red-50 px-4 py-2.5 text-sm text-red-600 dark:bg-red-950/40 dark:text-red-400">{error}</p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-lg bg-brand-500 py-2.5 text-sm font-semibold text-white hover:bg-brand-600 disabled:opacity-60 transition-colors"
            >
              {loading ? 'Enviando...' : 'Enviar enlace'}
            </button>
          </form>

          <div className="mt-4 text-center">
            <Link to="/login" className="inline-flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300">
              <ArrowLeft className="h-3.5 w-3.5" />
              Volver al login
            </Link>
          </div>
        </div>
      </div>
    </div>
    </>
  )
}
