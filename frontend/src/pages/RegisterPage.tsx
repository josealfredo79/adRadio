import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '@/contexts/AuthContext'
import { Radio, Eye, EyeOff } from 'lucide-react'
import { getApiError } from '@/lib/api'
import SEO from '@/components/SEO'

export default function RegisterPage() {
  const { register } = useAuth()
  const navigate = useNavigate()
  const [form, setForm] = useState({ email: '', password: '', businessName: '' })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [showPwd, setShowPwd] = useState(false)

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setForm({ ...form, [e.target.name]: e.target.value })
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await register(form.email, form.password, form.businessName)
      navigate(`/verify-email?email=${encodeURIComponent(form.email)}`)
    } catch (err: unknown) {
      setError(getApiError(err, 'Error al registrarse'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      <SEO title="Registro" description="Crea tu cuenta gratuita en IaRadio y empieza a crear campañas por WhatsApp con IA." />
      <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-brand-50 to-indigo-100 px-4 dark:from-gray-950 dark:to-gray-900">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-500 shadow-lg">
            <Radio className="h-7 w-7 text-white" />
          </div>
          <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100">IaRadio</h1>
          <p className="mt-1 text-gray-500 dark:text-gray-400">Empieza gratis en menos de 2 minutos</p>
        </div>

        <div className="rounded-2xl bg-white p-8 shadow-xl dark:bg-gray-950 dark:border dark:border-gray-800">
          <h2 className="mb-6 text-xl font-semibold text-gray-900 dark:text-gray-100">Crear cuenta</h2>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">
                Nombre del negocio
              </label>
              <input
                name="businessName"
                type="text"
                required
                value={form.businessName}
                onChange={handleChange}
                className="w-full rounded-lg border border-gray-300 bg-white px-3.5 py-2.5 text-sm text-gray-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100 dark:placeholder-gray-500"
                placeholder="Ej: Restaurante La Paloma"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">Email</label>
              <input
                name="email"
                type="email"
                required
                value={form.email}
                onChange={handleChange}
                className="w-full rounded-lg border border-gray-300 bg-white px-3.5 py-2.5 text-sm text-gray-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100 dark:placeholder-gray-500"
                placeholder="tu@negocio.com"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">Contraseña</label>
              <div className="relative">
                <input
                  name="password"
                  type={showPwd ? 'text' : 'password'}
                  required
                  value={form.password}
                  onChange={handleChange}
                  className="w-full rounded-lg border border-gray-300 bg-white px-3.5 py-2.5 pr-10 text-sm text-gray-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100 dark:placeholder-gray-500"
                  placeholder="Mín. 8 caracteres, 1 mayúscula, 1 número"
                />
                <button
                  type="button"
                  onClick={() => setShowPwd(!showPwd)}
                  aria-label={showPwd ? 'Ocultar contraseña' : 'Mostrar contraseña'}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
                >
                  {showPwd ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            {error && (
              <div className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-600 dark:bg-red-950/40 dark:text-red-400">{error}</div>
            )}

            <p className="text-xs text-gray-400 dark:text-gray-500">
              Al registrarte aceptas nuestros{' '}
              <Link to="/terms" className="text-brand-600 hover:underline dark:text-brand-400">Términos de uso</Link>{' '}
              y{' '}
              <Link to="/privacy" className="text-brand-600 hover:underline dark:text-brand-400">Política de privacidad</Link>.
            </p>

            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-lg bg-brand-500 py-2.5 text-sm font-medium text-white shadow hover:bg-brand-600 disabled:opacity-60 transition-colors"
            >
              {loading ? 'Creando cuenta...' : 'Crear cuenta gratis'}
            </button>
          </form>

          <p className="mt-6 text-center text-sm text-gray-500 dark:text-gray-400">
            ¿Ya tienes cuenta?{' '}
            <Link to="/login" className="font-medium text-brand-600 hover:underline dark:text-brand-400">
              Inicia sesión
            </Link>
          </p>
        </div>
      </div>
    </div>
    </>
  )
}
