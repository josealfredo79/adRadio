import { Link } from 'react-router-dom'
import { Radio } from 'lucide-react'

export default function LandingFooter() {
  return (
    <footer className="border-t border-white/5 px-5 py-10">
      <div className="mx-auto flex max-w-5xl flex-col items-center gap-5 sm:flex-row sm:justify-between">
        <div className="flex items-center gap-2.5">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-[#674CC4] to-[#6366F1]">
            <Radio className="h-3.5 w-3.5 text-white" />
          </div>
          <span className="font-black text-white">IaRadio</span>
          <span className="text-gray-600 text-sm">— Spots de radio con IA para WhatsApp</span>
        </div>
        <div className="flex flex-col gap-2 text-sm text-gray-600 sm:items-end">
          <div>
            <strong>Contacto:</strong> <a href="mailto:iaradio@iaradio.online" className="hover:text-indigo-400 underline">iaradio@iaradio.online</a>
          </div>
          <div>
            <strong>Dirección fiscal:</strong><br />
            Callejón del Bohemio No. 8A, Depto. 7 Altos, Col. Ricardo Flores Magón,<br />
            Heroica Ciudad de Tlaxiaco, Oaxaca, C.P. 69800<br />
            Entre calles: Tierra y Libertad
          </div>
        </div>
      </div>
      <div className="mx-auto mt-6 flex max-w-5xl flex-col items-center gap-2 sm:flex-row sm:justify-between">
        <div className="flex gap-5 text-sm text-gray-600">
          <Link to="/terms" className="hover:text-gray-300 transition-colors">Términos</Link>
          <Link to="/privacy" className="hover:text-gray-300 transition-colors">Privacidad</Link>
          <Link to="/login" className="hover:text-gray-300 transition-colors">Iniciar sesión</Link>
          <Link to="/register" className="hover:text-gray-300 transition-colors">Registrarse</Link>
        </div>
      </div>
      <p className="mt-6 text-center text-xs text-gray-700">© {new Date().getFullYear()} IaRadio. Hecho con ❤️ en México.</p>
    </footer>
  )
}
