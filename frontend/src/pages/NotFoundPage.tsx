import { Link } from 'react-router-dom'

export default function NotFoundPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-gray-50 px-4">
      <div className="text-center">
        <h1 className="text-8xl font-bold text-brand-500">404</h1>
        <p className="mt-4 text-xl text-gray-600">Página no encontrada</p>
        <p className="mt-2 text-gray-500">La página que buscas no existe o fue movida.</p>
        <Link
          to="/"
          className="mt-8 inline-block rounded-lg bg-brand-500 px-6 py-3 text-white hover:bg-brand-600"
        >
          Volver al inicio
        </Link>
      </div>
    </div>
  )
}
