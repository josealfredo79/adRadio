import { useState } from 'react'
import { useNavigate, useSearchParams, Link } from 'react-router-dom'
import api from '@/lib/api'
import { Radio, CheckCircle } from 'lucide-react'

export default function VerifyEmailPage() {
  const [params] = useSearchParams()
  const email = params.get('email') ?? ''
  const navigate = useNavigate()
  const [code, setCode] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [success, setSuccess] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await api.post('/auth/verify-email', { email, code })
      setSuccess(true)
      setTimeout(() => navigate('/login'), 2000)
    } catch (err: any) {
      setError(err.response?.data?.detail ?? 'Código inválido')
    } finally {
      setLoading(false)
    }
  }

  if (success) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-brand-50 to-indigo-100">
        <div className="rounded-2xl bg-white p-10 text-center shadow-xl">
          <CheckCircle className="mx-auto mb-4 h-14 w-14 text-green-500" />
          <h2 className="text-xl font-bold text-gray-900">¡Email verificado!</h2>
          <p className="mt-2 text-gray-500">Redirigiendo a login...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-brand-50 to-indigo-100 px-4">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-500 shadow-lg">
            <Radio className="h-7 w-7 text-white" />
          </div>
        </div>
        <div className="rounded-2xl bg-white p-8 shadow-xl">
          <h2 className="mb-2 text-xl font-semibold text-gray-900">Verifica tu email</h2>
          <p className="mb-6 text-sm text-gray-500">
            Enviamos un código de 6 dígitos a <strong>{email}</strong>. Expira en 10 minutos.
          </p>
          <form onSubmit={handleSubmit} className="space-y-4">
            <input
              type="text"
              maxLength={6}
              required
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
              className="w-full rounded-lg border border-gray-300 px-3.5 py-3 text-center text-2xl font-bold tracking-widest focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20"
              placeholder="000000"
            />
            {error && (
              <div className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-600">{error}</div>
            )}
            <button
              type="submit"
              disabled={loading || code.length !== 6}
              className="w-full rounded-lg bg-brand-500 py-2.5 text-sm font-medium text-white shadow hover:bg-brand-600 disabled:opacity-60 transition-colors"
            >
              {loading ? 'Verificando...' : 'Verificar'}
            </button>
          </form>
          <p className="mt-4 text-center text-sm text-gray-500">
            <Link to="/register" className="text-brand-600 hover:underline">Volver al registro</Link>
          </p>
        </div>
      </div>
    </div>
  )
}
