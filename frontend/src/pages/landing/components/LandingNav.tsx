import { Link } from 'react-router-dom'
import { Radio } from 'lucide-react'

export default function LandingNav() {
  return (
    <nav className="sticky top-0 z-50 glass">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-4">
        <div className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-[#674CC4] to-[#6366F1] shadow-lg shadow-indigo-500/30">
            <Radio className="h-4 w-4 text-white" />
          </div>
          <span className="text-lg font-black tracking-tight">IaRadio</span>
        </div>
        <div className="hidden items-center gap-7 text-sm text-gray-400 sm:flex">
          <a href="#como-funciona" className="hover:text-white transition-colors">Cómo funciona</a>
          <a href="#precios" className="hover:text-white transition-colors">Precios</a>
          <a href="#faq" className="hover:text-white transition-colors">FAQ</a>
        </div>
        <div className="flex items-center gap-3">
          <Link to="/login" className="text-sm text-gray-400 hover:text-white transition-colors">
            Iniciar sesión
          </Link>
          <Link
            to="/register"
            className="rounded-xl bg-gradient-to-r from-[#674CC4] to-[#6366F1] px-5 py-2 text-sm font-bold text-white shadow-lg shadow-indigo-500/30 hover:shadow-indigo-500/50 hover:scale-105 transition-all"
          >
            Prueba gratis →
          </Link>
        </div>
      </div>
    </nav>
  )
}
